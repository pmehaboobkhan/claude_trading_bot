"""Same-symbol signal consolidation.

Two strategies in the v1 portfolio can both target GLD: `dual_momentum_taa`
when gold is the top-momentum risk asset, and `gold_permanent_overlay`'s
permanent 10% allocation. Without consolidation the routine layer would
attempt two ENTRY positions on the same symbol, double-booking. The macro-ETF
position cap in `risk_limits.yaml` catches it implicitly, but the catch is
fragile and produces ambiguous decision artifacts.

This module does the consolidation **deterministically and explicitly**:
when multiple strategies emit ENTRY on the same symbol, the strategy with
the larger allocation is **primary** and the others are recorded as
`subsumed_strategies` — preserved for auditability but routed to a NO_TRADE
decision file with `reason: subsumed_by_<primary>`.

Design notes:

- EXIT signals are NEVER subsumed. EXITs reduce risk and always pass through.
- ENTRY + EXIT on the same symbol → both signals preserved with `conflict=True`
  so the routine layer can surface the conflict as an URGENT operator alert.
  v1 doesn't auto-resolve this case; it's a genuine ambiguity that warrants
  human review.
- `STRATEGY_ALLOCATIONS` is a constant here because the percentages live in
  prose descriptions inside `config/strategy_rules.yaml`, not as structured
  fields. A separate `prompts/proposed_updates/` draft proposes adding a
  structured `allocation_pct` field; until that lands and gets PR-merged,
  the constant below is the source of truth.

References:
- `lib/signals.py > Signal` — the input dataclass.
- `prompts/routines/end_of_day.md` — the canonical consumer (after the
  proposed update in `prompts/proposed_updates/2026-05-14_eod_signal_consolidation.md`
  is PR-merged).
- `plan.md > "Daily-layer ensemble/voting framework"` — this is the first
  deliverable of that work item.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lib.signals import Signal

# Fallback allocation table — kept as a transitional safety net so the module
# stays usable without a strategy_rules.yaml in scope (unit tests, tools that
# don't load config). Production callers should pass `strategy_rules` to
# `consolidate()` so the live source of truth is
# `config/strategy_rules.yaml > allowed_strategies > <name> > allocation_pct`.
STRATEGY_ALLOCATIONS: dict[str, float] = {
    "dual_momentum_taa": 0.60,
    "large_cap_momentum_top5": 0.30,
    "gold_permanent_overlay": 0.10,
}

# Used as a tie-breaker if two strategies have identical allocations: lexical
# order by strategy name. Stable and reproducible.


@dataclass
class ConsolidatedSignal:
    symbol: str
    action: str                              # ENTRY | EXIT | HOLD | NO_SIGNAL
    primary_strategy: str
    subsumed_strategies: list[str] = field(default_factory=list)
    contributing_signals: list[Signal] = field(default_factory=list)
    rationale: str = ""
    conflict: bool = False                   # True when ENTRY+EXIT collide

    @property
    def is_subsumed(self) -> bool:
        """Convenience: True if this ConsolidatedSignal absorbed one or more
        other strategies on the same symbol+action."""
        return len(self.subsumed_strategies) > 0


def _allocation_for(strategy: str, strategy_rules: dict | None = None) -> float:
    """Look up the allocation pct for a strategy.

    Reads `strategy_rules > allowed_strategies > <strategy> > allocation_pct`
    when ``strategy_rules`` is provided. Falls back to ``STRATEGY_ALLOCATIONS``
    when the config is absent or the field is missing (transitional safety
    net). Unknown strategies receive 0.0 — they cannot win a same-symbol tie
    against any known strategy, which is the safest default.
    """
    if strategy_rules is not None:
        for entry in strategy_rules.get("allowed_strategies", []):
            if entry.get("name") == strategy and "allocation_pct" in entry:
                return float(entry["allocation_pct"])
    return STRATEGY_ALLOCATIONS.get(strategy, 0.0)


def _pick_primary(
    signals: list[Signal],
    strategy_rules: dict | None = None,
) -> Signal:
    """Pick the primary signal from a group with the same (symbol, action).

    Tie-breakers (in order):
      1. Highest allocation_pct (from config when available, else
         STRATEGY_ALLOCATIONS fallback).
      2. Lexically smallest strategy name (deterministic).
    """
    return min(
        signals,
        key=lambda s: (-_allocation_for(s.strategy, strategy_rules), s.strategy),
    )


def consolidate(
    signals: list[Signal],
    strategy_rules: dict | None = None,
) -> list[ConsolidatedSignal]:
    """Consolidate same-symbol signals from multiple strategies.

    Rules:
      - Group by (symbol, action).
      - ENTRY group with N > 1 strategies → one ConsolidatedSignal where the
        highest-allocation strategy is primary; the rest go to `subsumed_strategies`.
      - EXIT group with N > 1 strategies → one ConsolidatedSignal per group;
        the primary is still the highest-allocation strategy, but `subsumed`
        is misleading for exits (all exits are intentional risk-reducers). In
        v1 we treat the EXIT group the same way for symmetry; the routine
        layer should perform the exit once and acknowledge that all
        contributing strategies have flipped.
      - ENTRY on symbol X + EXIT on symbol X (same symbol, different actions)
        → two ConsolidatedSignals, both with `conflict=True`. Routine layer
        must surface for human review; v1 does not auto-resolve.
      - HOLD / NO_SIGNAL signals pass through unchanged (one ConsolidatedSignal
        per raw signal, no subsumption).

    Args:
      signals: raw signals as produced by `signals.evaluate_all`.
      strategy_rules: optional parsed `config/strategy_rules.yaml`. When
        provided, allocation lookups read from
        `allowed_strategies[*].allocation_pct`; otherwise the
        ``STRATEGY_ALLOCATIONS`` fallback table is used.

    Returns:
      List of ConsolidatedSignal objects, ordered by (symbol, action) for
      deterministic output. Order of the input list does not affect output.
    """
    # Group by symbol → action → list of Signal
    by_symbol: dict[str, dict[str, list[Signal]]] = {}
    for sig in signals:
        by_symbol.setdefault(sig.symbol, {}).setdefault(sig.action, []).append(sig)

    out: list[ConsolidatedSignal] = []

    for symbol in sorted(by_symbol.keys()):
        actions_map = by_symbol[symbol]
        has_entry = "ENTRY" in actions_map
        has_exit = "EXIT" in actions_map
        conflict = has_entry and has_exit

        for action in sorted(actions_map.keys()):
            group = actions_map[action]
            if action in ("ENTRY", "EXIT"):
                primary = _pick_primary(group, strategy_rules)
                subsumed = [s.strategy for s in group if s.strategy != primary.strategy]
                rationale = primary.rationale
                if subsumed:
                    rationale = (
                        f"{primary.rationale} "
                        f"[consolidated: subsumes {', '.join(sorted(subsumed))} "
                        f"on {symbol} {action}]"
                    )
                out.append(ConsolidatedSignal(
                    symbol=symbol,
                    action=action,
                    primary_strategy=primary.strategy,
                    subsumed_strategies=sorted(subsumed),
                    # Sort contributing_signals by strategy so output is
                    # independent of input order (locked in by test_input_order_does_not_affect_output).
                    contributing_signals=sorted(group, key=lambda s: s.strategy),
                    rationale=rationale,
                    conflict=conflict,
                ))
            else:
                # HOLD / NO_SIGNAL: pass through unchanged, no grouping
                for sig in group:
                    out.append(ConsolidatedSignal(
                        symbol=symbol,
                        action=action,
                        primary_strategy=sig.strategy,
                        subsumed_strategies=[],
                        contributing_signals=[sig],
                        rationale=sig.rationale,
                        conflict=False,
                    ))

    return out
