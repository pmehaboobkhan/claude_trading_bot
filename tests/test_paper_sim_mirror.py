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
    # Log row reflects the broker fill price + slippage (audit trail)
    assert fill.simulated_price == round(broker_fill, 4)
    assert "broker_fill=100.0500" in fill.notes
    assert "order_id=ord_X" in fill.notes
    # Alpaca is the source of truth — open_position must NOT write positions.json
    # in alpaca mode (the reconcile mirror owns it).
    assert paper_sim._read_positions() == {}


def test_open_position_alpaca_mode_pending_records_no_sim_fallback(monkeypatch, isolated_dir):
    """The real Monday case: order submitted at 16:30 is accepted but does NOT
    fill in the poll window (market closed; fills next open). It must NOT fall
    back to a synthetic sim price and must NOT write positions.json — it
    records a PENDING_BROKER breadcrumb. Alpaca will fill it next open and the
    reconcile mirror will pick it up."""
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    with patch.object(paper_sim, "_alpaca_submit_and_wait",
                      return_value=(None, {"id": "ord_P", "status": "accepted"})):
        fill = paper_sim.open_position(
            symbol="SPY", side="BUY", quantity=10, quote_price=100.0,
            rationale_link="decisions/2026-05-18/eod_SPY.json",
            stop_loss=90.0, take_profit=120.0,
        )
    assert fill.status == "PENDING_BROKER"
    assert "order_id=ord_P" in fill.notes
    assert "fell back to sim price" not in fill.notes
    assert paper_sim._read_positions() == {}


def test_sync_positions_from_broker_mirrors_alpaca(monkeypatch, isolated_dir):
    """positions.json becomes an exact mirror of Alpaca's actual positions
    (long-only → side BUY; entry = avg_entry_price)."""
    import lib.broker as real_broker
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    monkeypatch.setattr(real_broker, "get_positions", lambda: [
        {"symbol": "SPY", "qty": 12.0, "avg_entry_price": 501.25,
         "market_value": 6100.0, "unrealized_pl": 85.0},
        {"symbol": "GLD", "qty": 4.0, "avg_entry_price": 210.0,
         "market_value": 850.0, "unrealized_pl": 10.0},
    ])
    n = paper_sim.sync_positions_from_broker()
    pos = paper_sim._read_positions()
    assert n == 2
    assert pos["SPY"]["quantity"] == 12.0
    assert pos["SPY"]["entry_price"] == 501.25
    assert pos["SPY"]["side"] == "BUY"
    assert set(pos) == {"SPY", "GLD"}


def test_reconcile_alpaca_mode_mirrors_broker_no_divergence(monkeypatch, isolated_dir):
    """In alpaca mode reconcile() syncs positions.json FROM Alpaca and reports
    no divergence — Alpaca is authoritative, so step 8a's compare trivially
    passes and the routine never false-halts on an in-flight order."""
    import lib.broker as real_broker
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    # local stale/empty; Alpaca has the real (next-open-filled) position
    monkeypatch.setattr(real_broker, "get_positions", lambda: [
        {"symbol": "SPY", "qty": 10.0, "avg_entry_price": 500.0,
         "market_value": 5000.0, "unrealized_pl": 0.0}])
    rec = paper_sim.reconcile()
    assert rec["discrepancies"] == []
    assert rec["open_count"] == 1
    assert paper_sim._read_positions()["SPY"]["quantity"] == 10.0


def test_reconcile_sim_mode_unchanged(monkeypatch, isolated_dir):
    """Regression guard: sim mode reconcile() keeps the log-vs-positions
    behavior and never calls the broker."""
    monkeypatch.delenv("BROKER_PAPER", raising=False)
    with patch.object(paper_sim, "sync_positions_from_broker") as mocked:
        paper_sim.open_position(
            symbol="SPY", side="BUY", quantity=5, quote_price=100.0,
            rationale_link="decisions/2026-05-18/s.json",
            stop_loss=90.0, take_profit=120.0)
        rec = paper_sim.reconcile()
    mocked.assert_not_called()
    assert rec["open_count"] == 1
    assert rec["discrepancies"] == []


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


def _stage_pending_moc(monkeypatch, *, order_id="ord_A", symbol="SPY",
                       side="BUY", qty=10):
    """Helper: put one PENDING_MOC row in the log via submit_moc_entry."""
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    import lib.broker as real_broker
    monkeypatch.setattr(
        real_broker, "submit_moc_order",
        lambda s, *, qty, side, client_order_id=None: {
            "id": order_id, "status": "accepted", "is_paper": True},
    )
    return paper_sim.submit_moc_entry(
        symbol=symbol, side=side, quantity=qty,
        rationale_link=f"decisions/2026-05-18/1550_{symbol}.json",
        stop_loss=90.0, take_profit=120.0,
    )


def test_confirm_moc_fills_finalizes_filled_order(monkeypatch, isolated_dir):
    """Phase 2: a filled MOC becomes an OPEN position at the auction price,
    positions.json reflects it, and reconcile() shows no divergence."""
    _stage_pending_moc(monkeypatch, order_id="ord_A", symbol="SPY", qty=10)
    import lib.broker as real_broker
    monkeypatch.setattr(real_broker, "get_order", lambda oid: {
        "id": oid, "status": "filled", "filled_avg_price": 101.25,
        "filled_qty": 10.0})

    summary = paper_sim.confirm_moc_fills()

    assert "SPY" in summary["confirmed"]
    pos = paper_sim._read_positions()
    assert pos["SPY"]["quantity"] == 10
    assert pos["SPY"]["entry_price"] == 101.25
    # reconcile() is now Alpaca-authoritative: it mirrors the broker account.
    monkeypatch.setattr(real_broker, "get_positions", lambda: [
        {"symbol": "SPY", "qty": 10.0, "avg_entry_price": 101.25,
         "market_value": 1012.5, "unrealized_pl": 0.0}])
    rec = paper_sim.reconcile()
    assert rec["open_count"] == 1
    assert rec["discrepancies"] == []


def test_confirm_moc_fills_rejected_order_is_no_trade(monkeypatch, isolated_dir):
    """A rejected MOC must NOT become a synthetic fill — it's NO_TRADE."""
    _stage_pending_moc(monkeypatch, order_id="ord_R", symbol="GLD", qty=5)
    import lib.broker as real_broker
    monkeypatch.setattr(real_broker, "get_order", lambda oid: {
        "id": oid, "status": "rejected", "filled_avg_price": None})

    summary = paper_sim.confirm_moc_fills()

    assert "GLD" in summary["rejected"]
    assert paper_sim._read_positions() == {}
    monkeypatch.setattr(real_broker, "get_positions", lambda: [])
    rec = paper_sim.reconcile()
    assert rec["open_count"] == 0
    assert rec["discrepancies"] == []


def test_confirm_moc_fills_leaves_unfilled_order_pending(monkeypatch, isolated_dir):
    """Called before the auction completes: order still accepted, not filled.
    Must not finalize — no OPEN, no REJECTED, position not created."""
    _stage_pending_moc(monkeypatch, order_id="ord_P", symbol="TLT", qty=7)
    import lib.broker as real_broker
    monkeypatch.setattr(real_broker, "get_order", lambda oid: {
        "id": oid, "status": "accepted", "filled_avg_price": None})

    summary = paper_sim.confirm_moc_fills()

    assert summary["still_pending"] == ["TLT"]
    assert summary["confirmed"] == [] and summary["rejected"] == []
    assert paper_sim._read_positions() == {}


def test_confirm_moc_fills_is_idempotent(monkeypatch, isolated_dir):
    """Re-running phase 2 after a fill must not double-open the position."""
    _stage_pending_moc(monkeypatch, order_id="ord_A", symbol="SPY", qty=10)
    import lib.broker as real_broker
    monkeypatch.setattr(real_broker, "get_order", lambda oid: {
        "id": oid, "status": "filled", "filled_avg_price": 101.25,
        "filled_qty": 10.0})

    first = paper_sim.confirm_moc_fills()
    second = paper_sim.confirm_moc_fills()

    assert first["confirmed"] == ["SPY"]
    assert second["confirmed"] == []  # already finalized — not re-confirmed
    monkeypatch.setattr(real_broker, "get_positions", lambda: [
        {"symbol": "SPY", "qty": 10.0, "avg_entry_price": 101.25,
         "market_value": 1012.5, "unrealized_pl": 0.0}])
    rec = paper_sim.reconcile()
    assert rec["open_count"] == 1
    assert rec["discrepancies"] == []


# ---- Phase-1 MOC submission (submit_moc_entry) --------------------------


def test_submit_moc_entry_writes_pending_row_without_polling(monkeypatch, isolated_dir):
    """Phase 1: submit an MOC entry. Must NOT poll for a fill (MOC fills at
    16:00, not now), MUST NOT touch positions.json, and records a
    PENDING_MOC breadcrumb row with the broker order id."""
    monkeypatch.setenv("BROKER_PAPER", "alpaca")
    import lib.broker as real_broker
    calls = {}

    def fake_moc(symbol, *, qty, side, client_order_id=None):
        calls["args"] = (symbol, qty, side, client_order_id)
        return {"id": "ord_moc_1", "status": "accepted", "is_paper": True}

    monkeypatch.setattr(real_broker, "submit_moc_order", fake_moc)
    # If the code ever falls back to the 5s poll path, this blows up the test.
    with patch.object(paper_sim, "_alpaca_submit_and_wait",
                      side_effect=AssertionError("MOC must not poll in phase 1")):
        fill = paper_sim.submit_moc_entry(
            symbol="SPY", side="BUY", quantity=10,
            rationale_link="decisions/2026-05-18/1550_SPY.json",
            stop_loss=90.0, take_profit=120.0,
        )

    assert fill.status == "PENDING_MOC"
    assert calls["args"][0] == "SPY"
    assert calls["args"][1] == 10
    assert calls["args"][2] == "BUY"
    assert "ord_moc_1" in fill.notes
    # positions.json must remain empty — the position is not confirmed yet.
    assert paper_sim._read_positions() == {}


def test_submit_moc_entry_requires_alpaca_mode(monkeypatch, isolated_dir):
    """In sim mode the two-phase MOC flow does not apply (sim fills at the
    close via open_position). Calling submit_moc_entry must fail loudly."""
    monkeypatch.delenv("BROKER_PAPER", raising=False)
    with pytest.raises(ValueError, match="requires BROKER_PAPER=alpaca"):
        paper_sim.submit_moc_entry(
            symbol="SPY", side="BUY", quantity=10,
            rationale_link="decisions/2026-05-18/1550_SPY.json",
            stop_loss=90.0, take_profit=120.0,
        )


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
