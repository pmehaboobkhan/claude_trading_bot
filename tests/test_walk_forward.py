"""Pure-function tests for lib.walk_forward — no network, no backtest calls."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.walk_forward import generate_windows, select_best, aggregate_oos  # noqa: E402


def test_generate_windows_5y_is_1y_oos_step_1y():
    """Standard config: 5-year IS, 1-year OOS, advance by 1 year."""
    windows = generate_windows(
        full_start="2010-01-01", full_end="2020-01-01",
        is_years=5, oos_years=1, step_years=1,
    )
    # First IS: 2010 → 2015 (exclusive end), OOS: 2015 → 2016
    # Last IS:  2014 → 2019,                OOS: 2019 → 2020
    assert windows[0] == ("2010-01-01", "2015-01-01", "2015-01-01", "2016-01-01")
    assert windows[-1] == ("2014-01-01", "2019-01-01", "2019-01-01", "2020-01-01")
    assert len(windows) == 5  # 2015,16,17,18,19 OOS years


def test_generate_windows_rejects_window_past_end():
    """If OOS would extend past full_end, omit that fold."""
    windows = generate_windows(
        full_start="2010-01-01", full_end="2016-06-30",
        is_years=5, oos_years=1, step_years=1,
    )
    # IS 2010→2015, OOS 2015→2016 fits. IS 2011→2016, OOS 2016→2017 does NOT fit (2017 > 2016-06-30).
    assert len(windows) == 1


def test_select_best_picks_highest_sharpe():
    """select_best returns the params dict with highest Sharpe from candidates."""
    candidates = [
        {"params": {"h": 0.08}, "metrics": {"sharpe": 0.9, "cagr": 10.0, "mdd": 12.0}},
        {"params": {"h": 0.07}, "metrics": {"sharpe": 1.2, "cagr": 11.0, "mdd": 13.0}},
        {"params": {"h": 0.09}, "metrics": {"sharpe": 1.1, "cagr": 12.0, "mdd": 14.0}},
    ]
    best = select_best(candidates, by="sharpe")
    assert best["params"] == {"h": 0.07}


def test_select_best_with_dd_constraint_rejects_winners_over_cap():
    """If a candidate breaches the DD cap, it cannot be selected even with best Sharpe."""
    candidates = [
        {"params": {"h": 0.08}, "metrics": {"sharpe": 1.5, "cagr": 11.0, "mdd": 18.0}},
        {"params": {"h": 0.07}, "metrics": {"sharpe": 1.1, "cagr": 10.0, "mdd": 13.0}},
    ]
    best = select_best(candidates, by="sharpe", max_mdd_pct=15.0)
    assert best["params"] == {"h": 0.07}, "should reject the high-Sharpe high-DD winner"


def test_select_best_raises_when_no_candidate_satisfies_dd_cap():
    import pytest
    candidates = [
        {"params": {"h": 0.08}, "metrics": {"sharpe": 1.5, "cagr": 11.0, "mdd": 18.0}},
    ]
    with pytest.raises(ValueError, match="max_mdd_pct"):
        select_best(candidates, by="sharpe", max_mdd_pct=15.0)


def test_aggregate_oos_chain_concatenates_returns():
    """OOS aggregator concatenates daily returns across folds and reports headline metrics."""
    folds = [
        {"oos_daily_returns": [0.0004] * 252,
         "oos_metrics": {"sharpe": 1.0, "cagr": 10.5, "mdd": 5.0}},
        {"oos_daily_returns": [0.0003] * 252,
         "oos_metrics": {"sharpe": 0.9, "cagr": 7.8, "mdd": 4.0}},
    ]
    agg = aggregate_oos(folds)
    assert "chained_cagr" in agg
    assert "chained_mdd" in agg
    assert "chained_sharpe" in agg
    assert "n_days" in agg
    assert agg["n_days"] == 504
    # Roughly: average of 8% and 10% CAGR-ish, somewhere in between
    assert 7.0 < agg["chained_cagr"] < 12.0


def test_aggregate_oos_empty_returns_zeros():
    """No folds → all-zero aggregate, no crash."""
    agg = aggregate_oos([])
    assert agg["n_days"] == 0
    assert agg["chained_cagr"] == 0.0
    assert agg["chained_mdd"] == 0.0
    assert agg["chained_sharpe"] == 0.0


def test_daily_returns_from_curve_computes_pct_changes():
    """daily_returns_from_curve returns (curve[i] / curve[i-1]) - 1 per pair."""
    from scripts.run_walk_forward import daily_returns_from_curve
    curve = [("2020-01-01", 100.0), ("2020-01-02", 101.0), ("2020-01-03", 102.01)]
    returns = daily_returns_from_curve(curve)
    assert len(returns) == 2
    assert abs(returns[0] - 0.01) < 1e-9
    assert abs(returns[1] - 0.01) < 1e-9


def test_daily_returns_from_curve_empty_or_single_returns_empty():
    from scripts.run_walk_forward import daily_returns_from_curve
    assert daily_returns_from_curve([]) == []
    assert daily_returns_from_curve([("2020-01-01", 100.0)]) == []
