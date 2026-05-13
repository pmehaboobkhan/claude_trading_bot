"""Tests for the live-trading gate evaluator.

All tests use synthetic inputs (no real CB history, no real bars).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.live_trading_gate import (  # noqa: E402
    GateConfig, GateInputs, evaluate_gates, has_cb_throttle_event,
    has_spy_trend_flip, has_vix_high_observed, distinct_calendar_months,
)


def _config(**overrides):
    base = dict(
        enabled=True,
        minimum_paper_trading_days=90,
        minimum_paper_trades=30,
        minimum_sharpe=0.8,
        maximum_drawdown_pct=12.0,
        regime_diversity_enabled=True,
        require_cb_throttle_event=True,
        require_spy_trend_flip=True,
        require_vix_high_observed=25.0,
        minimum_distinct_months=4,
    )
    base.update(overrides)
    return GateConfig(**base)


def test_has_cb_throttle_event_true_when_history_has_full_to_half():
    history = [
        {"timestamp": "2026-02-01T12:00:00+00:00",
         "from_state": "FULL", "to_state": "HALF", "dd_pct": 8.5,
         "observed_equity": 91500.0, "peak_equity": 100000.0},
    ]
    assert has_cb_throttle_event(history) is True


def test_has_cb_throttle_event_false_on_empty_history():
    assert has_cb_throttle_event([]) is False


def test_has_cb_throttle_event_ignores_recovery_only():
    """A HALF->FULL recovery alone (with no preceding throttle) doesn't count."""
    history = [
        {"timestamp": "2026-03-01T12:00:00+00:00",
         "from_state": "HALF", "to_state": "FULL", "dd_pct": 4.0,
         "observed_equity": 96000.0, "peak_equity": 100000.0},
    ]
    assert has_cb_throttle_event(history) is False


def test_has_spy_trend_flip_true_when_filter_changed_state():
    snapshots = [
        {"date": "2026-01-15", "spy_above_10mo_sma": True},
        {"date": "2026-02-15", "spy_above_10mo_sma": True},
        {"date": "2026-03-15", "spy_above_10mo_sma": False},
        {"date": "2026-04-15", "spy_above_10mo_sma": False},
    ]
    assert has_spy_trend_flip(snapshots) is True


def test_has_spy_trend_flip_false_when_always_above():
    snapshots = [
        {"date": "2026-01-15", "spy_above_10mo_sma": True},
        {"date": "2026-02-15", "spy_above_10mo_sma": True},
        {"date": "2026-03-15", "spy_above_10mo_sma": True},
    ]
    assert has_spy_trend_flip(snapshots) is False


def test_has_vix_high_observed_true_when_any_close_at_or_above_threshold():
    snapshots = [
        {"date": "2026-01-15", "vix_close": 18.0},
        {"date": "2026-02-15", "vix_close": 26.5},
        {"date": "2026-03-15", "vix_close": 19.0},
    ]
    assert has_vix_high_observed(snapshots, threshold=25.0) is True


def test_has_vix_high_observed_false_when_all_below():
    snapshots = [
        {"date": "2026-01-15", "vix_close": 14.0},
        {"date": "2026-02-15", "vix_close": 22.0},
    ]
    assert has_vix_high_observed(snapshots, threshold=25.0) is False


def test_distinct_calendar_months():
    snapshots = [
        {"date": "2026-01-15"}, {"date": "2026-01-28"},
        {"date": "2026-02-03"}, {"date": "2026-04-19"},
    ]
    assert distinct_calendar_months(snapshots) == 3  # Jan, Feb, Apr


def test_evaluate_gates_all_pass():
    cfg = _config()
    inputs = GateInputs(
        paper_trading_days=120,
        closed_paper_trades=45,
        portfolio_sharpe=1.05,
        portfolio_max_drawdown_pct=10.5,
        cb_history=[
            {"timestamp": "2026-02-01T12:00:00+00:00", "from_state": "FULL",
             "to_state": "HALF", "dd_pct": 8.5,
             "observed_equity": 91500.0, "peak_equity": 100000.0},
        ],
        daily_snapshots=[
            {"date": "2026-01-15", "spy_above_10mo_sma": True, "vix_close": 18.0},
            {"date": "2026-02-15", "spy_above_10mo_sma": False, "vix_close": 27.0},
            {"date": "2026-03-15", "spy_above_10mo_sma": False, "vix_close": 22.0},
            {"date": "2026-04-15", "spy_above_10mo_sma": False, "vix_close": 20.0},
        ],
    )
    verdict = evaluate_gates(cfg, inputs)
    assert verdict.overall_pass is True
    assert all(g.passed for g in verdict.gates)


def test_evaluate_gates_fails_on_missing_cb_event():
    cfg = _config()
    inputs = GateInputs(
        paper_trading_days=120,
        closed_paper_trades=45,
        portfolio_sharpe=1.05,
        portfolio_max_drawdown_pct=10.5,
        cb_history=[],  # no throttle ever fired
        daily_snapshots=[
            {"date": f"2026-{m:02}-15", "spy_above_10mo_sma": (m % 2 == 0),
             "vix_close": 27.0 if m == 2 else 18.0}
            for m in range(1, 6)
        ],
    )
    verdict = evaluate_gates(cfg, inputs)
    assert verdict.overall_pass is False
    failures = [g.name for g in verdict.gates if not g.passed]
    assert "cb_throttle_event" in failures


def test_evaluate_gates_disabled_returns_pass_with_warning():
    cfg = _config(enabled=False)
    inputs = GateInputs(
        paper_trading_days=10, closed_paper_trades=2,
        portfolio_sharpe=0.1, portfolio_max_drawdown_pct=20.0,
        cb_history=[], daily_snapshots=[],
    )
    verdict = evaluate_gates(cfg, inputs)
    assert verdict.overall_pass is True
    assert verdict.warning is not None
    assert "disabled" in verdict.warning.lower()
