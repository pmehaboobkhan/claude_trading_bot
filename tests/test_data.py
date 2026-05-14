"""Tests for lib.data routing logic.

Network-dependent paths (the actual yfinance + Alpaca calls) are mocked.
We verify the routing decision and the dict-shape contract.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import data as ld  # noqa: E402


def test_bar_source_default_is_yfinance(monkeypatch):
    monkeypatch.delenv("BAR_SOURCE", raising=False)
    assert ld._bar_source() == "yfinance"


def test_bar_source_env_override_to_alpaca(monkeypatch):
    monkeypatch.setenv("BAR_SOURCE", "alpaca")
    assert ld._bar_source() == "alpaca"


def test_bar_source_env_override_case_insensitive(monkeypatch):
    monkeypatch.setenv("BAR_SOURCE", "ALPACA")
    assert ld._bar_source() == "alpaca"


def test_get_bars_daily_routes_to_yfinance_by_default(monkeypatch):
    monkeypatch.delenv("BAR_SOURCE", raising=False)
    sentinel = [{"ts": "2026-05-13T00:00:00+00:00", "open": 1, "high": 2,
                 "low": 0.5, "close": 1.5, "volume": 100}]
    with patch.object(ld, "_get_bars_yfinance", return_value=sentinel) as mock_yf, \
         patch.object(ld, "_get_bars_alpaca") as mock_alpaca:
        out = ld.get_bars("SPY", timeframe="1Day", limit=300)
    assert out == sentinel
    mock_yf.assert_called_once_with("SPY", limit=300)
    mock_alpaca.assert_not_called()


def test_get_bars_daily_routes_to_alpaca_when_env_set(monkeypatch):
    monkeypatch.setenv("BAR_SOURCE", "alpaca")
    sentinel = [{"ts": "2026-05-13T00:00:00+00:00", "open": 1, "high": 2,
                 "low": 0.5, "close": 1.5, "volume": 100}]
    with patch.object(ld, "_get_bars_alpaca", return_value=sentinel) as mock_alpaca, \
         patch.object(ld, "_get_bars_yfinance") as mock_yf:
        out = ld.get_bars("SPY", timeframe="1Day", limit=300)
    assert out == sentinel
    mock_alpaca.assert_called_once_with("SPY", timeframe="1Day", limit=300)
    mock_yf.assert_not_called()


def test_get_bars_intraday_always_alpaca(monkeypatch):
    """Intraday (1Hour, 5Min) bars MUST use Alpaca regardless of BAR_SOURCE."""
    monkeypatch.delenv("BAR_SOURCE", raising=False)  # default = yfinance
    sentinel = [{"ts": "2026-05-13T13:30:00+00:00", "open": 1, "high": 2,
                 "low": 0.5, "close": 1.5, "volume": 100}]
    for tf in ("1Hour", "5Min"):
        with patch.object(ld, "_get_bars_alpaca", return_value=sentinel) as mock_alpaca, \
             patch.object(ld, "_get_bars_yfinance") as mock_yf:
            out = ld.get_bars("SPY", timeframe=tf, limit=50)
        assert out == sentinel
        mock_alpaca.assert_called_once_with("SPY", timeframe=tf, limit=50)
        mock_yf.assert_not_called()


def test_calendar_days_for_daily():
    """1.5x trading-day buffer + 5 calendar-day pad."""
    assert ld._calendar_days_for("1Day", 100) == 155
    assert ld._calendar_days_for("1Day", 300) == 455


def test_calendar_days_for_intraday():
    assert ld._calendar_days_for("1Hour", 100) == int(100 / 7 * 1.5) + 5
    # 5Min for 100 bars: int(100/78 * 1.5) = 1, +5 = 6; floored at 7.
    assert ld._calendar_days_for("5Min", 100) == 7
    # 5Min for 1000 bars: int(1000/78 * 1.5) = 19, +5 = 24; well above floor.
    assert ld._calendar_days_for("5Min", 1000) == 24


def test_calendar_days_for_unknown_raises():
    import pytest
    with pytest.raises(ValueError, match="unsupported timeframe"):
        ld._calendar_days_for("1Week", 10)


def test_get_bars_yfinance_returns_canonical_dict_shape(monkeypatch):
    """Mock yfinance.download to verify output shape conformance."""
    import pandas as pd
    monkeypatch.delenv("BAR_SOURCE", raising=False)

    fake_df = pd.DataFrame({
        "Open": [100.0, 101.0],
        "High": [102.0, 103.0],
        "Low": [99.0, 100.5],
        "Close": [101.0, 102.5],
        "Volume": [1_000_000, 1_100_000],
    }, index=pd.to_datetime(["2026-05-12", "2026-05-13"]))

    fake_yf = type(sys)("yfinance")
    fake_yf.download = lambda *a, **kw: fake_df
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    bars = ld._get_bars_yfinance("SPY", limit=10)
    assert len(bars) == 2
    for b in bars:
        assert set(b.keys()) == {"ts", "open", "high", "low", "close", "volume"}
        assert isinstance(b["ts"], str)
        assert isinstance(b["volume"], int)
        for k in ("open", "high", "low", "close"):
            assert isinstance(b[k], float)
    assert bars[0]["close"] == 101.0
    assert bars[-1]["close"] == 102.5


def test_get_bars_yfinance_truncates_to_limit(monkeypatch):
    """If yfinance returns more bars than requested, take the most recent N."""
    import pandas as pd
    fake_df = pd.DataFrame({
        "Open": [1, 2, 3, 4, 5],
        "High": [1, 2, 3, 4, 5],
        "Low": [1, 2, 3, 4, 5],
        "Close": [1, 2, 3, 4, 5],
        "Volume": [1, 2, 3, 4, 5],
    }, index=pd.to_datetime(["2026-05-09", "2026-05-10", "2026-05-11", "2026-05-12", "2026-05-13"]))
    fake_yf = type(sys)("yfinance")
    fake_yf.download = lambda *a, **kw: fake_df
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    bars = ld._get_bars_yfinance("SPY", limit=2)
    assert len(bars) == 2
    assert bars[0]["close"] == 4.0
    assert bars[1]["close"] == 5.0


def test_get_bars_yfinance_empty_returns_empty(monkeypatch):
    import pandas as pd
    fake_yf = type(sys)("yfinance")
    fake_yf.download = lambda *a, **kw: pd.DataFrame()
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    assert ld._get_bars_yfinance("BAD", limit=10) == []
