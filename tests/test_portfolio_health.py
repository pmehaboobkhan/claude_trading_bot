"""Unit tests for lib/portfolio_health.py — per-position invalidation logic
used by the market_open / midday / pre_close monitoring routines.

Run with: pytest tests/test_portfolio_health.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import portfolio_health
from lib.portfolio_health import (
    PositionHealth,
    assess_positions,
    health_as_dict,
    positions_to_close,
)


def _write_positions(tmp_path: Path, positions: dict[str, dict]) -> Path:
    """Write a positions.json file at tmp_path/positions.json."""
    p = tmp_path / "positions.json"
    p.write_text(json.dumps(positions), encoding="utf-8")
    return p


def _long_position(entry: float, stop: float | None = None,
                  target: float | None = None, qty: float = 100) -> dict:
    return {
        "side": "BUY",
        "quantity": qty,
        "entry_price": entry,
        "entry_ts": "2026-05-12T13:30:00Z",
        "stop_loss": stop,
        "take_profit": target,
        "rationale_link": "decisions/2026-05-12/1630_TEST.json",
    }


def _short_position(entry: float, stop: float | None = None,
                   target: float | None = None, qty: float = 100) -> dict:
    return {
        "side": "SELL",
        "quantity": qty,
        "entry_price": entry,
        "entry_ts": "2026-05-12T13:30:00Z",
        "stop_loss": stop,
        "take_profit": target,
        "rationale_link": "decisions/2026-05-12/1630_TEST.json",
    }


# ---------------------------------------------------------------------------
# Long-position scenarios
# ---------------------------------------------------------------------------

def test_long_position_in_profit_within_targets(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, target=200.0, qty=50),
    })
    [h] = assess_positions({"AAPL": 190.0}, positions_path=p)
    assert h.symbol == "AAPL"
    assert h.side == "BUY"
    assert h.pnl_pct == pytest.approx((190 - 180) / 180)
    assert h.pnl_usd == pytest.approx(50 * 10)
    assert h.stop_breached is False
    assert h.target_hit is False
    assert h.invalidation_triggers == []
    assert h.should_close() is False


def test_long_position_breaches_stop(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, target=200.0, qty=50),
    })
    [h] = assess_positions({"AAPL": 169.5}, positions_path=p)
    assert h.stop_breached is True
    assert h.target_hit is False
    assert "stop_loss breached" in h.invalidation_triggers[0]
    assert h.should_close() is True
    assert h.pnl_usd == pytest.approx(-525.0)  # 50 * (169.5 - 180)


def test_long_position_hits_target(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, target=200.0, qty=50),
    })
    [h] = assess_positions({"AAPL": 200.5}, positions_path=p)
    assert h.stop_breached is False
    assert h.target_hit is True
    assert "take_profit hit" in h.invalidation_triggers[0]
    assert h.should_close() is True


def test_long_position_at_exact_stop_threshold_triggers(tmp_path) -> None:
    # Boundary: quote == stop_loss → counts as breached for long.
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, qty=50),
    })
    [h] = assess_positions({"AAPL": 170.0}, positions_path=p)
    assert h.stop_breached is True


# ---------------------------------------------------------------------------
# Short-position scenarios (defensive — short selling is disabled in v1 but
# the math should still be correct so we don't silently mis-assess if it
# ever gets enabled)
# ---------------------------------------------------------------------------

def test_short_position_in_profit(tmp_path) -> None:
    # Short at 100, price drops to 90 → profit.
    p = _write_positions(tmp_path, {
        "XYZ": _short_position(entry=100.0, stop=110.0, target=90.0, qty=10),
    })
    [h] = assess_positions({"XYZ": 90.5}, positions_path=p)
    assert h.side == "SELL"
    assert h.pnl_usd == pytest.approx(10 * (100 - 90.5))
    assert h.stop_breached is False
    assert h.target_hit is False  # target=90, quote=90.5 — not yet


def test_short_position_breaches_stop(tmp_path) -> None:
    # Short at 100 with stop at 110. Price rises to 110.5 → stop breached.
    p = _write_positions(tmp_path, {
        "XYZ": _short_position(entry=100.0, stop=110.0, qty=10),
    })
    [h] = assess_positions({"XYZ": 110.5}, positions_path=p)
    assert h.stop_breached is True
    assert h.should_close() is True


def test_short_position_hits_target(tmp_path) -> None:
    # Short at 100, target 90. Price drops to 89 → target hit.
    p = _write_positions(tmp_path, {
        "XYZ": _short_position(entry=100.0, target=90.0, qty=10),
    })
    [h] = assess_positions({"XYZ": 89.0}, positions_path=p)
    assert h.target_hit is True
    assert h.should_close() is True


# ---------------------------------------------------------------------------
# Positions without stops/targets (Strategy A / Strategy C)
# ---------------------------------------------------------------------------

def test_position_without_stops_or_targets_never_triggers(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "GLD": _long_position(entry=180.0, stop=None, target=None, qty=10),
    })
    # Down 10% — still no invalidation because no stop is configured.
    [h] = assess_positions({"GLD": 162.0}, positions_path=p)
    assert h.stop_breached is False
    assert h.target_hit is False
    assert h.invalidation_triggers == []
    assert h.should_close() is False
    # PnL still computed.
    assert h.pnl_pct == pytest.approx(-0.10)


# ---------------------------------------------------------------------------
# Multiple positions, mixed states
# ---------------------------------------------------------------------------

def test_assess_positions_mixed_book(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, target=200.0, qty=50),    # OK
        "MSFT": _long_position(entry=400.0, stop=380.0, target=440.0, qty=25),    # stop
        "GLD":  _long_position(entry=180.0, stop=None, target=None, qty=20),       # no stops
    })
    healthy_book = assess_positions(
        {"AAPL": 190.0, "MSFT": 379.0, "GLD": 185.0}, positions_path=p,
    )
    by_sym = {h.symbol: h for h in healthy_book}
    assert by_sym["AAPL"].should_close() is False
    assert by_sym["MSFT"].should_close() is True
    assert by_sym["GLD"].should_close() is False


def test_positions_to_close_filters_correctly(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, qty=50),     # OK
        "MSFT": _long_position(entry=400.0, stop=380.0, qty=25),     # stop
        "TSLA": _long_position(entry=250.0, target=300.0, qty=10),   # target
    })
    closes = positions_to_close(
        {"AAPL": 175.0, "MSFT": 379.0, "TSLA": 305.0}, positions_path=p,
    )
    symbols = {c.symbol for c in closes}
    assert symbols == {"MSFT", "TSLA"}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_missing_quote_raises(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, qty=50),
    })
    with pytest.raises(KeyError, match="no quote provided"):
        assess_positions({}, positions_path=p)


def test_empty_book_returns_empty_list(tmp_path) -> None:
    p = _write_positions(tmp_path, {})
    assert assess_positions({}, positions_path=p) == []


def test_no_positions_file_returns_empty(tmp_path) -> None:
    assert assess_positions({}, positions_path=tmp_path / "missing.json") == []


def test_invalid_side_raises(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": {
            "side": "WAT",   # invalid
            "quantity": 10,
            "entry_price": 180.0,
            "entry_ts": "2026-05-12T13:30:00Z",
            "stop_loss": 170.0,
            "take_profit": 200.0,
            "rationale_link": "x",
        },
    })
    with pytest.raises(ValueError, match="unknown side"):
        assess_positions({"AAPL": 175.0}, positions_path=p)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_health_as_dict_returns_json_friendly(tmp_path) -> None:
    p = _write_positions(tmp_path, {
        "AAPL": _long_position(entry=180.0, stop=170.0, qty=50),
    })
    [h] = assess_positions({"AAPL": 175.0}, positions_path=p)
    d = health_as_dict(h)
    json.dumps(d)  # must serialize without error
    assert d["symbol"] == "AAPL"
    assert d["invalidation_triggers"] == []
    assert "should_close" not in d  # method, not a serialized field


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
