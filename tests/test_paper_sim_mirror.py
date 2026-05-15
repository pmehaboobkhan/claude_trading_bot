"""Tests for lib.paper_sim BROKER_PAPER=alpaca mirror behavior.

The default sim mode is exercised implicitly across the wider test suite.
These tests focus specifically on the mirror routing + slippage capture.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import paper_sim  # noqa: E402


@pytest.fixture
def isolated_dir(monkeypatch, tmp_path):
    """Redirect log + positions paths to a tmp dir per test."""
    monkeypatch.setattr(paper_sim, "PAPER_DIR", tmp_path)
    monkeypatch.setattr(paper_sim, "LOG_PATH", tmp_path / "log.csv")
    monkeypatch.setattr(paper_sim, "POSITIONS_PATH", tmp_path / "positions.json")
    return tmp_path


def test_broker_mode_default_is_sim(monkeypatch):
    monkeypatch.delenv("BROKER_PAPER", raising=False)
    assert paper_sim.broker_mode() == "sim"


def test_broker_mode_env_alpaca(monkeypatch):
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    assert paper_sim.broker_mode() == "alpaca"


def test_broker_mode_env_case_insensitive(monkeypatch):
    monkeypatch.setenv("BROKER_PAPER", "ALPACA")
    assert paper_sim.broker_mode() == "alpaca"


def test_client_order_id_derives_from_rationale_link():
    coid = paper_sim._client_order_id("decisions/2026-05-14/0935_SPY.json", "open")
    assert coid == "decisions_2026-05-14_0935_SPY_open"


def test_client_order_id_truncates_at_128_chars():
    long_link = "decisions/" + "a" * 200 + ".json"
    coid = paper_sim._client_order_id(long_link, "close")
    assert len(coid) <= 128


def test_open_position_sim_mode_does_not_call_broker(monkeypatch, isolated_dir):
    """Default sim mode never reaches lib.broker."""
    monkeypatch.delenv("BROKER_PAPER", raising=False)
    with patch.object(paper_sim, "_alpaca_submit_and_wait") as mock_submit:
        fill = paper_sim.open_position(
            symbol="SPY", side="BUY", quantity=10, quote_price=100.0,
            rationale_link="decisions/2026-05-14/test.json",
            stop_loss=90.0, take_profit=120.0,
        )
    mock_submit.assert_not_called()
    assert fill.status == "OPEN"
    assert fill.simulated_price > 0


def test_open_position_alpaca_mode_calls_broker_and_uses_broker_price(monkeypatch, isolated_dir):
    """Alpaca mode submits an order and uses the broker fill price."""
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    broker_fill = 100.05
    with patch.object(paper_sim, "_alpaca_submit_and_wait",
                      return_value=(broker_fill, {"id": "ord_X", "status": "filled"})):
        fill = paper_sim.open_position(
            symbol="SPY", side="BUY", quantity=10, quote_price=100.0,
            rationale_link="decisions/2026-05-14/test.json",
            stop_loss=90.0, take_profit=120.0,
        )
    # Log should reflect the broker fill price, not the sim price
    assert fill.simulated_price == round(broker_fill, 4)
    # Notes should include slippage vs sim
    assert "broker_fill=100.0500" in fill.notes
    assert "slippage_vs_sim=" in fill.notes
    assert "order_id=ord_X" in fill.notes


def test_open_position_alpaca_mode_falls_back_to_sim_on_failure(monkeypatch, isolated_dir):
    """If broker submit fails (returns None), use the sim price + log the failure."""
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    with patch.object(paper_sim, "_alpaca_submit_and_wait",
                      return_value=(None, {"error": "rejected"})):
        fill = paper_sim.open_position(
            symbol="SPY", side="BUY", quantity=10, quote_price=100.0,
            rationale_link="decisions/2026-05-14/test.json",
            stop_loss=90.0, take_profit=120.0,
        )
    # Sim price = 100.0 + 1bp slippage + 1bp half-spread = 100.02
    assert 100.0 < fill.simulated_price < 100.05  # close to sim price, not 100 exactly
    assert "broker_submit_failed" in fill.notes
    assert "fell back to sim price" in fill.notes


def test_close_position_alpaca_mode_uses_opposite_side(monkeypatch, isolated_dir):
    """Closing a BUY position must submit a SELL order to the broker."""
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    # First open with sim mode to establish position
    monkeypatch.delenv("BROKER_PAPER", raising=False)
    paper_sim.open_position(
        symbol="SPY", side="BUY", quantity=10, quote_price=100.0,
        rationale_link="decisions/2026-05-14/open.json",
        stop_loss=90.0, take_profit=120.0,
    )

    # Switch to alpaca mode for close
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    captured = {}
    def fake_submit(*, symbol, qty, side, client_order_id):
        captured["side"] = side
        captured["qty"] = qty
        captured["coid"] = client_order_id
        return 102.50, {"id": "ord_close", "status": "filled"}

    with patch.object(paper_sim, "_alpaca_submit_and_wait", side_effect=fake_submit):
        close_fill = paper_sim.close_position(
            symbol="SPY", quote_price=102.0,
            rationale_link="decisions/2026-05-14/close.json",
        )

    assert captured["side"] == "SELL"
    assert captured["qty"] == 10
    assert "close" in captured["coid"]
    assert close_fill.simulated_price == 102.50
    assert close_fill.realized_pnl > 0  # profit on the close
    assert "broker_close=102.5000" in close_fill.notes


def test_alpaca_submit_and_wait_returns_none_on_broker_error(monkeypatch):
    """Broker exceptions during submit must be swallowed (return None, not raise)."""
    fake_broker = type(sys)("broker")
    class FakeBrokerError(Exception): pass
    fake_broker.BrokerError = FakeBrokerError
    def fake_submit(*a, **kw):
        raise FakeBrokerError("creds missing")
    fake_broker.submit_market_order = fake_submit

    fake_lib = type(sys)("lib")
    fake_lib.broker = fake_broker
    monkeypatch.setitem(sys.modules, "lib", fake_lib)
    monkeypatch.setitem(sys.modules, "lib.broker", fake_broker)

    price, ack = paper_sim._alpaca_submit_and_wait(
        symbol="SPY", qty=10, side="BUY", client_order_id="test_open",
    )
    assert price is None
    assert "error" in ack
