"""Tests for per-strategy fill timing in lib.backtest.

`fill_timing="close"` is the default and MUST reproduce the historical
close-fill behaviour (the canonical 8-10%/Sharpe validation depends on it).
`fill_timing="next_open"` models the realistic execution for
large_cap_momentum_top5 (signal from close[D], fill at open[D+1]) — the path
chosen after the MOC signal-proxy gate showed its ranking needs the exact
close, so it cannot fill at that close.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import backtest  # noqa: E402


def _b(ts, open_, close):
    return {"ts": ts, "open": open_, "high": max(open_, close) + 1,
            "low": min(open_, close) - 1, "close": close, "volume": 1}


def _bars():
    # index:  0                1                2                3
    return [
        _b("2026-01-02T00:00:00+00:00", 10.0, 10.5),
        _b("2026-01-05T00:00:00+00:00", 10.6, 11.0),
        _b("2026-01-06T00:00:00+00:00", 11.2, 11.8),
        _b("2026-01-07T00:00:00+00:00", 11.9, 12.4),
    ]


def test_fill_quote_close_uses_current_bar_close():
    assert backtest._fill_quote(_bars(), 1, fill_timing="close") == 11.0
    assert backtest._fill_quote(_bars(), 2, fill_timing="close") == 11.8


def test_fill_quote_next_open_uses_next_bar_open():
    # decision at index 1 (close 11.0) -> fill at index 2 open (11.2)
    assert backtest._fill_quote(_bars(), 1, fill_timing="next_open") == 11.2
    assert backtest._fill_quote(_bars(), 2, fill_timing="next_open") == 11.9


def test_fill_quote_next_open_falls_back_to_close_at_series_end():
    # last index: no next bar -> fall back to this bar's close (no lookahead
    # invented; end-of-data liquidation uses the last known close)
    last = len(_bars()) - 1
    assert backtest._fill_quote(_bars(), last, fill_timing="next_open") == 12.4


def test_fill_quote_rejects_unknown_timing():
    with pytest.raises(ValueError, match="fill_timing"):
        backtest._fill_quote(_bars(), 0, fill_timing="teleport")
