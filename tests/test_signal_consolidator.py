"""Unit tests for lib/signal_consolidator.py — same-symbol signal consolidation.

The consolidator is deterministic by design: same input → same output, and
input order does not affect output. These tests lock in those properties
plus the specific GLD-convergence case that motivated the module.

Run with: pytest tests/test_signal_consolidator.py -v
"""
from __future__ import annotations

import random

from lib.signal_consolidator import ConsolidatedSignal, consolidate
from lib.signals import Signal


def _sig(symbol: str, action: str, strategy: str, rationale: str = "") -> Signal:
    return Signal(
        symbol=symbol,
        action=action,
        strategy=strategy,
        confidence_inputs={},
        confirmations_passed=[],
        confirmations_failed=[],
        rationale=rationale or f"{strategy}:{symbol}:{action}",
        timestamp="2026-05-14T20:00:00+00:00",
    )


def test_gld_convergence_taa_wins_over_overlay() -> None:
    """The canonical case: both strategies ENTRY on GLD → TAA primary, overlay subsumed."""
    signals = [
        _sig("GLD", "ENTRY", "dual_momentum_taa"),
        _sig("GLD", "ENTRY", "gold_permanent_overlay"),
    ]

    result = consolidate(signals)

    assert len(result) == 1
    cs = result[0]
    assert cs.symbol == "GLD"
    assert cs.action == "ENTRY"
    assert cs.primary_strategy == "dual_momentum_taa"
    assert cs.subsumed_strategies == ["gold_permanent_overlay"]
    assert cs.is_subsumed is True
    assert "subsumes gold_permanent_overlay" in cs.rationale
    assert cs.conflict is False


def test_overlay_alone_is_primary_no_subsumption() -> None:
    """Only the overlay fires on GLD (TAA chose SPY or cash) → overlay is primary, no subsumption."""
    signals = [
        _sig("SPY", "ENTRY", "dual_momentum_taa"),
        _sig("GLD", "ENTRY", "gold_permanent_overlay"),
    ]

    result = consolidate(signals)

    assert len(result) == 2
    by_sym = {cs.symbol: cs for cs in result}
    assert by_sym["GLD"].primary_strategy == "gold_permanent_overlay"
    assert by_sym["GLD"].subsumed_strategies == []
    assert by_sym["GLD"].is_subsumed is False
    assert by_sym["SPY"].primary_strategy == "dual_momentum_taa"
    assert by_sym["SPY"].subsumed_strategies == []


def test_distinct_symbols_no_subsumption() -> None:
    """Two strategies pointing at different symbols → two ConsolidatedSignals, no merging."""
    signals = [
        _sig("SPY", "ENTRY", "dual_momentum_taa"),
        _sig("NVDA", "ENTRY", "large_cap_momentum_top5"),
        _sig("GLD", "ENTRY", "gold_permanent_overlay"),
    ]

    result = consolidate(signals)

    assert len(result) == 3
    assert all(cs.is_subsumed is False for cs in result)
    assert sorted(cs.symbol for cs in result) == ["GLD", "NVDA", "SPY"]


def test_entry_and_exit_on_same_symbol_both_preserved_with_conflict() -> None:
    """TAA EXITs GLD while overlay ENTERs → both kept, conflict=True on each."""
    signals = [
        _sig("GLD", "EXIT", "dual_momentum_taa"),
        _sig("GLD", "ENTRY", "gold_permanent_overlay"),
    ]

    result = consolidate(signals)

    assert len(result) == 2
    for cs in result:
        assert cs.conflict is True, f"missing conflict flag on {cs.action}"
    by_action = {cs.action: cs for cs in result}
    assert by_action["EXIT"].primary_strategy == "dual_momentum_taa"
    assert by_action["ENTRY"].primary_strategy == "gold_permanent_overlay"


def test_three_strategies_same_symbol_highest_alloc_wins() -> None:
    """Hypothetical three-way ENTRY → highest-allocation primary, other two subsumed."""
    signals = [
        _sig("GLD", "ENTRY", "gold_permanent_overlay"),
        _sig("GLD", "ENTRY", "large_cap_momentum_top5"),
        _sig("GLD", "ENTRY", "dual_momentum_taa"),
    ]

    result = consolidate(signals)

    assert len(result) == 1
    cs = result[0]
    assert cs.primary_strategy == "dual_momentum_taa"
    # subsumed list is sorted alphabetically for determinism
    assert cs.subsumed_strategies == ["gold_permanent_overlay", "large_cap_momentum_top5"]


def test_input_order_does_not_affect_output() -> None:
    """Property test: shuffling input → identical output."""
    base = [
        _sig("GLD", "ENTRY", "dual_momentum_taa"),
        _sig("GLD", "ENTRY", "gold_permanent_overlay"),
        _sig("SPY", "ENTRY", "large_cap_momentum_top5"),
        _sig("AAPL", "EXIT", "large_cap_momentum_top5"),
    ]
    reference = consolidate(list(base))

    rng = random.Random(42)
    for _ in range(20):
        shuffled = list(base)
        rng.shuffle(shuffled)
        got = consolidate(shuffled)
        assert got == reference, "consolidator output depends on input order"


def test_no_signal_passes_through_unchanged() -> None:
    """NO_SIGNAL / HOLD pass through; no grouping or subsumption."""
    signals = [
        _sig("GLD", "NO_SIGNAL", "dual_momentum_taa", rationale="no momentum"),
        _sig("GLD", "NO_SIGNAL", "gold_permanent_overlay", rationale="rebalance window not open"),
    ]

    result = consolidate(signals)

    assert len(result) == 2
    for cs in result:
        assert cs.action == "NO_SIGNAL"
        assert cs.is_subsumed is False


def test_empty_input_yields_empty_output() -> None:
    assert consolidate([]) == []


def test_unknown_strategy_treated_as_zero_allocation() -> None:
    """A strategy not in STRATEGY_ALLOCATIONS cannot win a tie."""
    signals = [
        _sig("XYZ", "ENTRY", "experimental_thing"),       # unknown → 0.0 allocation
        _sig("XYZ", "ENTRY", "gold_permanent_overlay"),   # known → 0.10 allocation
    ]

    result = consolidate(signals)

    assert len(result) == 1
    assert result[0].primary_strategy == "gold_permanent_overlay"
    assert result[0].subsumed_strategies == ["experimental_thing"]


def test_consolidated_signal_carries_contributing_signals() -> None:
    """The Signal objects that contributed to a consolidation are preserved
    on `contributing_signals` for audit-trail purposes."""
    s1 = _sig("GLD", "ENTRY", "dual_momentum_taa")
    s2 = _sig("GLD", "ENTRY", "gold_permanent_overlay")

    result = consolidate([s1, s2])

    assert len(result) == 1
    contrib = result[0].contributing_signals
    assert len(contrib) == 2
    strategies = {s.strategy for s in contrib}
    assert strategies == {"dual_momentum_taa", "gold_permanent_overlay"}


def test_only_overlay_no_taa_no_subsumption() -> None:
    """If TAA doesn't fire at all on GLD (e.g. cash-floor regime), the overlay
    is primary on its own."""
    signals = [_sig("GLD", "ENTRY", "gold_permanent_overlay")]

    result = consolidate(signals)

    assert len(result) == 1
    assert result[0].primary_strategy == "gold_permanent_overlay"
    assert result[0].subsumed_strategies == []
    assert result[0].conflict is False
