"""Tests for lib.broker order-placement methods.

Network calls + alpaca-py imports are mocked. Verifies routing, payload
construction, and error handling.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import broker  # noqa: E402


@pytest.fixture(autouse=True)
def paper_creds(monkeypatch):
    """Provide synthetic paper credentials for every test."""
    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "test_key")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "test_secret")
    yield


def _fake_order(**overrides):
    base = dict(
        id="ord_123",
        client_order_id="dec_456",
        symbol="SPY",
        qty=10.0,
        filled_qty=0.0,
        filled_avg_price=None,
        side="BUY",
        status="accepted",
        submitted_at=SimpleNamespace(isoformat=lambda: "2026-05-14T13:30:00Z"),
        filled_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---- submit_market_order ------------------------------------------------


def test_submit_market_order_returns_dict_with_order_fields(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, *a, **kw): captured["init"] = kw
        def submit_order(self, *, order_data):
            captured["order_data"] = order_data
            return _fake_order()

    fake_alpaca_client = type(sys)("alpaca.trading.client")
    fake_alpaca_client.TradingClient = FakeClient
    fake_alpaca_enums = type(sys)("alpaca.trading.enums")
    fake_alpaca_enums.OrderSide = SimpleNamespace(BUY="BUY", SELL="SELL")
    fake_alpaca_enums.TimeInForce = SimpleNamespace(DAY="day")
    fake_alpaca_requests = type(sys)("alpaca.trading.requests")
    fake_alpaca_requests.MarketOrderRequest = lambda **kw: SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules, "alpaca.trading.client", fake_alpaca_client)
    monkeypatch.setitem(sys.modules, "alpaca.trading.enums", fake_alpaca_enums)
    monkeypatch.setitem(sys.modules, "alpaca.trading.requests", fake_alpaca_requests)
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")

    result = broker.submit_market_order(
        "SPY", qty=10, side="BUY", client_order_id="dec_456"
    )
    assert result["id"] == "ord_123"
    assert result["client_order_id"] == "dec_456"
    assert result["symbol"] == "SPY"
    assert result["qty"] == 10.0
    assert result["side"] == "BUY"
    assert result["status"] == "accepted"
    assert result["is_paper"] is True


def test_submit_market_order_rejects_invalid_side(monkeypatch):
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")
    with pytest.raises(broker.BrokerError, match="invalid side"):
        broker.submit_market_order("SPY", qty=10, side="HOLD")


def test_submit_market_order_rejects_zero_qty(monkeypatch):
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")
    with pytest.raises(broker.BrokerError, match="qty must be positive"):
        broker.submit_market_order("SPY", qty=0, side="BUY")


def test_submit_market_order_refused_in_halted_mode(monkeypatch):
    monkeypatch.setattr(broker, "current_mode", lambda: "HALTED")
    with pytest.raises(broker.BrokerError, match="broker access refused"):
        broker.submit_market_order("SPY", qty=10, side="BUY")


# ---- submit_moc_order (Market-On-Close) ---------------------------------


def test_submit_moc_order_uses_cls_time_in_force(monkeypatch):
    """A Market-On-Close order must be built with TimeInForce.CLS so it fills
    in the official closing auction (the price the backtest assumes)."""
    captured = {}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        def submit_order(self, *, order_data):
            captured["order_data"] = order_data
            return _fake_order(status="accepted")

    fake_alpaca_client = type(sys)("alpaca.trading.client")
    fake_alpaca_client.TradingClient = FakeClient
    fake_alpaca_enums = type(sys)("alpaca.trading.enums")
    fake_alpaca_enums.OrderSide = SimpleNamespace(BUY="BUY", SELL="SELL")
    fake_alpaca_enums.TimeInForce = SimpleNamespace(DAY="day", CLS="cls")
    fake_alpaca_requests = type(sys)("alpaca.trading.requests")
    fake_alpaca_requests.MarketOrderRequest = lambda **kw: SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules, "alpaca.trading.client", fake_alpaca_client)
    monkeypatch.setitem(sys.modules, "alpaca.trading.enums", fake_alpaca_enums)
    monkeypatch.setitem(sys.modules, "alpaca.trading.requests", fake_alpaca_requests)
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")

    result = broker.submit_moc_order(
        "SPY", qty=10, side="BUY", client_order_id="dec_moc_1"
    )
    assert captured["order_data"].time_in_force == "cls"
    assert captured["order_data"].symbol == "SPY"
    assert result["id"] == "ord_123"
    assert result["client_order_id"] == "dec_456"
    assert result["is_paper"] is True


def test_submit_moc_order_rejects_invalid_side(monkeypatch):
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")
    with pytest.raises(broker.BrokerError, match="invalid side"):
        broker.submit_moc_order("SPY", qty=10, side="HOLD")


def test_submit_moc_order_refused_in_halted_mode(monkeypatch):
    monkeypatch.setattr(broker, "current_mode", lambda: "HALTED")
    with pytest.raises(broker.BrokerError, match="broker access refused"):
        broker.submit_moc_order("SPY", qty=10, side="BUY")


# ---- get_order ----------------------------------------------------------


def test_get_order_returns_filled_state(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def get_order_by_id(self, oid):
            return _fake_order(
                id=oid,
                filled_qty=10.0,
                filled_avg_price=425.50,
                status="filled",
                filled_at=SimpleNamespace(isoformat=lambda: "2026-05-14T13:30:05Z"),
            )

    fake_alpaca_client = type(sys)("alpaca.trading.client")
    fake_alpaca_client.TradingClient = FakeClient
    monkeypatch.setitem(sys.modules, "alpaca.trading.client", fake_alpaca_client)
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")

    out = broker.get_order("ord_123")
    assert out["filled_qty"] == 10.0
    assert out["filled_avg_price"] == 425.50
    assert out["status"] == "filled"


def test_get_order_handles_unfilled(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def get_order_by_id(self, oid):
            return _fake_order(filled_avg_price=None, filled_qty=0.0, status="accepted")

    fake_alpaca_client = type(sys)("alpaca.trading.client")
    fake_alpaca_client.TradingClient = FakeClient
    monkeypatch.setitem(sys.modules, "alpaca.trading.client", fake_alpaca_client)
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")

    out = broker.get_order("ord_123")
    assert out["filled_avg_price"] is None
    assert out["filled_qty"] == 0.0


# ---- cancel_all_open_orders --------------------------------------------


def test_cancel_all_open_orders_returns_count(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def cancel_orders(self):
            return [object(), object(), object()]

    fake_alpaca_client = type(sys)("alpaca.trading.client")
    fake_alpaca_client.TradingClient = FakeClient
    monkeypatch.setitem(sys.modules, "alpaca.trading.client", fake_alpaca_client)
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")

    assert broker.cancel_all_open_orders() == 3


# ---- close_all_positions -----------------------------------------------


def test_close_all_positions_returns_close_orders(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def close_all_positions(self, cancel_orders=True):
            return [
                SimpleNamespace(id="ord_a", symbol="SPY", qty=10.0, side="SELL",
                                status="accepted"),
                SimpleNamespace(id="ord_b", symbol="GLD", qty=5.0, side="SELL",
                                status="accepted"),
            ]

    fake_alpaca_client = type(sys)("alpaca.trading.client")
    fake_alpaca_client.TradingClient = FakeClient
    monkeypatch.setitem(sys.modules, "alpaca.trading.client", fake_alpaca_client)
    monkeypatch.setattr(broker, "current_mode", lambda: "PAPER_TRADING")

    closes = broker.close_all_positions()
    assert len(closes) == 2
    assert {c["symbol"] for c in closes} == {"SPY", "GLD"}
    assert all(c["side"] == "SELL" for c in closes)
