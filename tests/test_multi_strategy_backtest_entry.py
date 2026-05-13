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
    """Sanity: callable form returns the expected metric keys."""
    result = mod.run_backtest(_default_args())
    assert isinstance(result, dict)
    for key in ("ann_return", "max_drawdown_pct", "sharpe", "final_equity",
                "cb_events", "n_trades"):
        assert key in result, f"missing key: {key}"
    # Sanity ranges (loose; just verifying we got real numbers)
    assert -100 < result["ann_return"] < 200
    assert 0 <= result["max_drawdown_pct"] <= 100


def test_run_backtest_no_report_when_write_report_false():
    """write_report=False must not create a file under backtests/."""
    args = _default_args(label="no_write_smoke")
    before = set((REPO_ROOT / "backtests" / "multi_strategy_portfolio").glob("*no_write_smoke*"))
    mod.run_backtest(args)
    after = set((REPO_ROOT / "backtests" / "multi_strategy_portfolio").glob("*no_write_smoke*"))
    assert before == after, "run_backtest wrote a report despite write_report=False"
