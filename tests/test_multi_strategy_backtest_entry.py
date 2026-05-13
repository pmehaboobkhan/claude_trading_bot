"""Verify run_multi_strategy_backtest.run_backtest() is callable in-process."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_multi_strategy_backtest as mod  # noqa: E402


def _default_args(**overrides):
    base = dict(
        start="2020-01-01",
        end="2021-12-31",
        capital=100_000.0,
        alloc_a=0.60, alloc_b=0.30, alloc_c=0.10,
        cash_buffer_pct=0.0,
        circuit_breaker=True,
        cb_half_dd=0.08, cb_out_dd=0.12,
        cb_recovery_dd=0.05, cb_out_recover_dd=0.08,
        label="test",
        write_report=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_run_backtest_returns_metrics_dict():
    """Sanity: callable form returns all 12 documented metric keys with expected types."""
    result = mod.run_backtest(_default_args())
    assert isinstance(result, dict)
    for key in ("ann_return", "max_drawdown_pct", "sharpe", "final_equity",
                "cb_events", "n_trades", "equity_curve",
                "overall", "hit_low", "hit_high", "dd_ok", "sharpe_ok"):
        assert key in result, f"missing key: {key}"
    # Sanity ranges (loose; just verifying we got real numbers)
    assert -100 < result["ann_return"] < 200
    assert 0 <= result["max_drawdown_pct"] <= 100
    # Type checks for structured/boolean keys
    assert isinstance(result["cb_events"], list)
    assert isinstance(result["n_trades"], int)
    assert isinstance(result["equity_curve"], list)
    assert isinstance(result["overall"], bool)
    assert isinstance(result["hit_low"], bool)
    assert isinstance(result["hit_high"], bool)
    assert isinstance(result["dd_ok"], bool)
    assert isinstance(result["sharpe_ok"], bool)


def test_run_backtest_no_report_when_write_report_false():
    """write_report=False must not create a file under backtests/."""
    args = _default_args(label="no_write_smoke")
    before = set((REPO_ROOT / "backtests" / "multi_strategy_portfolio").glob("*no_write_smoke*"))
    mod.run_backtest(args)
    after = set((REPO_ROOT / "backtests" / "multi_strategy_portfolio").glob("*no_write_smoke*"))
    assert before == after, "run_backtest wrote a report despite write_report=False"


def test_run_backtest_raises_on_bad_allocations():
    """Allocations that don't sum to 1.0 must raise ValueError (not silently exit 1)."""
    import pytest
    args = _default_args(alloc_a=0.5, alloc_b=0.5, alloc_c=0.5)  # sums to 1.5
    with pytest.raises(ValueError, match=r"alloc"):
        mod.run_backtest(args)


def test_run_backtest_raises_on_bad_cash_buffer():
    """cash_buffer_pct outside [0, 0.95) must raise ValueError."""
    import pytest
    args = _default_args(cash_buffer_pct=1.5)  # invalid
    with pytest.raises(ValueError, match=r"cash"):
        mod.run_backtest(args)
