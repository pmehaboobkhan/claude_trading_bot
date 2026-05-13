"""Live-trading unlock gate evaluator.

Pure functions over already-loaded inputs. Reading the underlying files
(circuit_breaker_history.jsonl, paper log, daily snapshots, config) is
the caller's responsibility — see `load_default_inputs()` for the
production assembly used by the monthly_review routine.

Used only by the monthly_review routine. The gate verdict is a
RECOMMENDATION input, not a permission system: human approval is still
required, and CLAUDE.md still locks live execution behind explicit PR.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class GateConfig:
    enabled: bool
    minimum_paper_trading_days: int
    minimum_paper_trades: int
    minimum_sharpe: float
    maximum_drawdown_pct: float
    regime_diversity_enabled: bool
    require_cb_throttle_event: bool
    require_spy_trend_flip: bool
    require_vix_high_observed: float  # threshold; e.g. 25.0
    minimum_distinct_months: int


@dataclass
class GateInputs:
    paper_trading_days: int
    closed_paper_trades: int
    portfolio_sharpe: float
    portfolio_max_drawdown_pct: float
    cb_history: list[dict]              # rows from circuit_breaker_history.jsonl
    daily_snapshots: list[dict]         # rows from memory/daily_snapshots/*.md (parsed)


@dataclass
class GateResult:
    name: str
    passed: bool
    actual: Any
    required: Any
    note: str = ""


@dataclass
class GateVerdict:
    overall_pass: bool
    gates: list[GateResult] = field(default_factory=list)
    warning: str | None = None  # set when disabled / when inputs are sparse


# ---- Individual gate predicates ----------------------------------------

THROTTLE_TRANSITIONS = {("FULL", "HALF"), ("HALF", "OUT"), ("FULL", "OUT")}


def has_cb_throttle_event(cb_history: list[dict]) -> bool:
    """At least one FULL→HALF, HALF→OUT, or FULL→OUT transition observed."""
    return any(
        (row.get("from_state"), row.get("to_state")) in THROTTLE_TRANSITIONS
        for row in cb_history
    )


def has_spy_trend_flip(snapshots: list[dict]) -> bool:
    """At least one change in `spy_above_10mo_sma` across the snapshot history."""
    states = [s.get("spy_above_10mo_sma") for s in snapshots
              if s.get("spy_above_10mo_sma") is not None]
    return len(set(states)) >= 2


def has_vix_high_observed(snapshots: list[dict], *, threshold: float) -> bool:
    """At least one daily VIX close at or above `threshold`."""
    return any(
        (s.get("vix_close") is not None) and (s["vix_close"] >= threshold)
        for s in snapshots
    )


def distinct_calendar_months(snapshots: list[dict]) -> int:
    """Number of distinct YYYY-MM keys present in snapshots."""
    months = set()
    for s in snapshots:
        d = s.get("date")
        if d and len(d) >= 7:
            months.add(d[:7])
    return len(months)


# ---- Top-level evaluator ----------------------------------------------


def evaluate_gates(config: GateConfig, inputs: GateInputs) -> GateVerdict:
    """Evaluate every gate and return a structured verdict.

    If `config.enabled` is False, returns overall_pass=True with a warning
    so the routine can surface that gates were bypassed by config.
    """
    if not config.enabled:
        return GateVerdict(
            overall_pass=True,
            gates=[],
            warning="Live-trading gates are disabled in config (gates.enabled=false)",
        )

    results: list[GateResult] = []

    # Existing floors
    results.append(GateResult(
        name="paper_trading_days",
        passed=inputs.paper_trading_days >= config.minimum_paper_trading_days,
        actual=inputs.paper_trading_days,
        required=config.minimum_paper_trading_days,
    ))
    results.append(GateResult(
        name="closed_paper_trades",
        passed=inputs.closed_paper_trades >= config.minimum_paper_trades,
        actual=inputs.closed_paper_trades,
        required=config.minimum_paper_trades,
    ))
    results.append(GateResult(
        name="portfolio_sharpe",
        passed=inputs.portfolio_sharpe >= config.minimum_sharpe,
        actual=round(inputs.portfolio_sharpe, 3),
        required=config.minimum_sharpe,
    ))
    results.append(GateResult(
        name="portfolio_max_drawdown",
        passed=inputs.portfolio_max_drawdown_pct <= config.maximum_drawdown_pct,
        actual=round(inputs.portfolio_max_drawdown_pct, 2),
        required=f"<= {config.maximum_drawdown_pct}",
    ))

    # Regime-diversity gates
    if config.regime_diversity_enabled:
        if config.require_cb_throttle_event:
            ok = has_cb_throttle_event(inputs.cb_history)
            results.append(GateResult(
                name="cb_throttle_event",
                passed=ok,
                actual=len(inputs.cb_history),
                required=">= 1 FULL->HALF or HALF->OUT transition",
                note="From trades/paper/circuit_breaker_history.jsonl",
            ))
        if config.require_spy_trend_flip:
            ok = has_spy_trend_flip(inputs.daily_snapshots)
            results.append(GateResult(
                name="spy_trend_flip",
                passed=ok,
                actual="observed" if ok else "no flip",
                required="At least one SPY 10mo-SMA filter change in window",
                note="From memory/daily_snapshots/<date>.md",
            ))
        if config.require_vix_high_observed > 0:
            ok = has_vix_high_observed(inputs.daily_snapshots,
                                       threshold=config.require_vix_high_observed)
            results.append(GateResult(
                name="vix_high_observed",
                passed=ok,
                actual=max((s.get("vix_close") or 0) for s in inputs.daily_snapshots) if inputs.daily_snapshots else 0,
                required=f">= {config.require_vix_high_observed}",
            ))
        n_months = distinct_calendar_months(inputs.daily_snapshots)
        results.append(GateResult(
            name="distinct_calendar_months",
            passed=n_months >= config.minimum_distinct_months,
            actual=n_months,
            required=config.minimum_distinct_months,
        ))

    overall = all(g.passed for g in results)
    return GateVerdict(overall_pass=overall, gates=results)


# ---- Production input loader (consumed by monthly_review prompt) -------


def load_default_inputs(*, performance_summary: dict) -> GateInputs:
    """Load gate inputs from canonical paths.

    `performance_summary` is supplied by the performance_review subagent and
    must contain: paper_trading_days, closed_paper_trades, portfolio_sharpe,
    portfolio_max_drawdown_pct.
    """
    history_path = REPO_ROOT / "trades" / "paper" / "circuit_breaker_history.jsonl"
    cb_history: list[dict] = []
    if history_path.exists():
        for line in history_path.read_text().splitlines():
            line = line.strip()
            if line:
                cb_history.append(json.loads(line))

    snapshots_dir = REPO_ROOT / "memory" / "daily_snapshots"
    daily_snapshots: list[dict] = []
    if snapshots_dir.exists():
        for snap_path in sorted(snapshots_dir.glob("*.md")):
            parsed = _parse_snapshot(snap_path)
            if parsed:
                daily_snapshots.append(parsed)

    return GateInputs(
        paper_trading_days=performance_summary["paper_trading_days"],
        closed_paper_trades=performance_summary["closed_paper_trades"],
        portfolio_sharpe=performance_summary["portfolio_sharpe"],
        portfolio_max_drawdown_pct=performance_summary["portfolio_max_drawdown_pct"],
        cb_history=cb_history,
        daily_snapshots=daily_snapshots,
    )


def _parse_snapshot(path: Path) -> dict | None:
    """Parse a daily snapshot for the fields we care about.

    Snapshots are markdown with a known structure; we extract just the
    date, spy_above_10mo_sma, and vix_close fields if present. Missing
    fields are tolerated (recorded as None).
    """
    text = path.read_text(encoding="utf-8")
    out: dict = {"date": path.stem, "spy_above_10mo_sma": None, "vix_close": None}
    for line in text.splitlines():
        # Conventional snapshot markers (extend as the snapshot format evolves):
        #   `- spy_above_10mo_sma: true`
        #   `- vix_close: 22.4`
        s = line.strip().lstrip("-* ").strip()
        if s.startswith("spy_above_10mo_sma:"):
            v = s.split(":", 1)[1].strip().lower()
            out["spy_above_10mo_sma"] = v in ("true", "yes", "1")
        elif s.startswith("vix_close:"):
            try:
                out["vix_close"] = float(s.split(":", 1)[1].strip())
            except ValueError:
                pass
    return out
