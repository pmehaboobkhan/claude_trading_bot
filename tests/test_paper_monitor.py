"""Unit tests for lib/paper_monitor.py.

Exercises each checker (log/positions reconciliation, circuit-breaker sanity,
risk-event window count, context-budget trend) and the aggregate exit-code
logic. All inputs are plain dicts / strings / tmp_path Path objects so the
checkers are tested without touching real /trades/paper/ files.

Run with: pytest tests/test_paper_monitor.py -v
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lib import paper_monitor as pm


# ---------------------------------------------------------------------------
# parse_trade_log
# ---------------------------------------------------------------------------

def test_parse_trade_log_drops_marker_rows_themselves():
    """The reset/marker row itself is never returned, even when standalone."""
    csv_text = """timestamp,symbol,side,quantity,status,notes
2026-05-12T20:03:00,RESET,N/A,0,MARKER,fresh-start
"""
    assert pm.parse_trade_log(csv_text) == []


def test_parse_trade_log_recognizes_underscore_reset_token():
    """Real-world reset row uses symbol=_RESET_ and status=RESET (see
    sync_alpaca_state.py 2026-05-15 entry in the live log)."""
    csv_text = """timestamp,symbol,side,quantity,simulated_price,rationale_link,stop_loss,take_profit,status,realized_pnl,notes
2026-05-12T20:00:00,GLD,BUY,34,430,...,387,538,OPEN,0,pre-reset
2026-05-15T00:31:53,_RESET_,RESET,0,0,scripts/sync_alpaca_state.py,,,RESET,0,fresh-start
2026-05-16T20:00:00,AAPL,BUY,10,200,...,180,250,OPEN,0,post-reset
"""
    rows = pm.parse_trade_log(csv_text)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"


def test_parse_trade_log_empty_string():
    rows = pm.parse_trade_log("timestamp,symbol,side,quantity,status\n")
    assert rows == []


def test_parse_trade_log_drops_pre_reset_rows():
    """RESET marker is a watershed: everything before it was closed at the
    broker side and emptied from positions.json. Only post-RESET rows are live."""
    csv_text = """timestamp,symbol,side,quantity,status,notes
2026-05-12T20:02:25,GLD,BUY,34,OPEN,pre-reset
2026-05-12T20:03:00,XOM,BUY,5,OPEN,pre-reset
2026-05-14T00:00:00,RESET,N/A,0,MARKER,fresh-start
2026-05-14T20:00:00,AAPL,BUY,10,OPEN,post-reset
"""
    rows = pm.parse_trade_log(csv_text)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"


def test_parse_trade_log_handles_log_with_no_resets():
    csv_text = """timestamp,symbol,side,quantity,status
2026-05-12T20:02:25,GLD,BUY,34,OPEN
2026-05-12T20:03:00,XOM,BUY,5,OPEN
"""
    rows = pm.parse_trade_log(csv_text)
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# check_log_positions_reconciliation
# ---------------------------------------------------------------------------

def _trade(symbol: str, side: str, qty: float, status: str = "OPEN") -> dict:
    return {
        "symbol": symbol, "side": side, "quantity": str(qty), "status": status,
    }


def test_reconciliation_passes_when_aligned():
    trades = [_trade("GLD", "BUY", 34), _trade("AAPL", "BUY", 10)]
    positions = {"GLD": {"quantity": 34}, "AAPL": {"quantity": 10}}
    finding = pm.check_log_positions_reconciliation(trades, positions)
    assert finding.severity == pm.OK


def test_reconciliation_fails_when_position_missing():
    trades = [_trade("GLD", "BUY", 34)]
    positions = {}  # no positions despite an open BUY
    finding = pm.check_log_positions_reconciliation(trades, positions)
    assert finding.severity == pm.FAIL
    assert "GLD" in finding.detail["only_in_log"]


def test_reconciliation_fails_when_extra_position():
    trades = []
    positions = {"AAPL": {"quantity": 10}}  # position with no buy in log
    finding = pm.check_log_positions_reconciliation(trades, positions)
    assert finding.severity == pm.FAIL
    assert "AAPL" in finding.detail["only_in_positions"]


def test_reconciliation_fails_on_quantity_mismatch():
    trades = [_trade("GLD", "BUY", 34)]
    positions = {"GLD": {"quantity": 30}}  # short 4 shares
    finding = pm.check_log_positions_reconciliation(trades, positions)
    assert finding.severity == pm.FAIL
    assert finding.detail["qty_mismatch"][0]["symbol"] == "GLD"


def test_reconciliation_ignores_closed_trades():
    """A BUY then a SELL that nets to zero should drop out of comparison."""
    trades = [
        _trade("GLD", "BUY", 34, status="CLOSED"),
        _trade("GLD", "SELL", 34, status="CLOSED"),
    ]
    positions = {}
    finding = pm.check_log_positions_reconciliation(trades, positions)
    assert finding.severity == pm.OK


def test_reconciliation_handles_qty_field_alias():
    """Some position records use 'qty' (Alpaca) vs 'quantity' (sim)."""
    trades = [_trade("GLD", "BUY", 34)]
    positions = {"GLD": {"qty": 34}}  # Alpaca-shaped record
    finding = pm.check_log_positions_reconciliation(trades, positions)
    assert finding.severity == pm.OK


# ---------------------------------------------------------------------------
# check_circuit_breaker
# ---------------------------------------------------------------------------

def test_cb_ok_when_full_and_peak_above_current():
    cb = {
        "state": "FULL",
        "peak_equity": 102000,
        "last_observed_equity": 101500,
        "updated_at": "2026-05-14T20:00:00Z",
    }
    finding = pm.check_circuit_breaker(cb)
    assert finding.severity == pm.OK
    assert finding.detail["drawdown_pct"] == 0.49


def test_cb_fail_on_unknown_state():
    finding = pm.check_circuit_breaker({"state": "MAYBE", "peak_equity": 100, "last_observed_equity": 100})
    assert finding.severity == pm.FAIL


def test_cb_fail_on_missing_fields():
    finding = pm.check_circuit_breaker({"state": "FULL"})
    assert finding.severity == pm.FAIL


def test_cb_fail_when_peak_below_current():
    """The state machine never ratchets peak down — this is impossible state."""
    finding = pm.check_circuit_breaker({
        "state": "FULL", "peak_equity": 100000, "last_observed_equity": 105000,
    })
    assert finding.severity == pm.FAIL


def test_cb_warn_when_empty():
    finding = pm.check_circuit_breaker({})
    assert finding.severity == pm.WARN


# ---------------------------------------------------------------------------
# check_risk_events_in_window
# ---------------------------------------------------------------------------

def test_risk_events_zero_in_window_is_ok(tmp_path):
    finding = pm.check_risk_events_in_window(
        [], date(2026, 5, 7), date(2026, 5, 14),
    )
    assert finding.severity == pm.OK
    assert finding.detail["files"] == []


def test_risk_events_under_threshold_is_ok(tmp_path):
    files = [tmp_path / "2026-05-13_120000_circuit_breaker.md",
             tmp_path / "2026-05-14_120000_circuit_breaker.md"]
    for f in files:
        f.write_text("")
    finding = pm.check_risk_events_in_window(
        files, date(2026, 5, 7), date(2026, 5, 14), warn_count=5,
    )
    assert finding.severity == pm.OK


def test_risk_events_at_threshold_warns(tmp_path):
    files = [tmp_path / f"2026-05-1{d}_120000_evt.md" for d in range(0, 5)]
    for f in files:
        f.write_text("")
    finding = pm.check_risk_events_in_window(
        files, date(2026, 5, 7), date(2026, 5, 14), warn_count=5,
    )
    assert finding.severity == pm.WARN
    assert len(finding.detail["files"]) == 5


def test_risk_events_outside_window_ignored(tmp_path):
    files = [
        tmp_path / "2026-04-01_120000_old.md",
        tmp_path / "2026-05-13_120000_in_window.md",
    ]
    for f in files:
        f.write_text("")
    finding = pm.check_risk_events_in_window(
        files, date(2026, 5, 7), date(2026, 5, 14),
    )
    assert finding.detail["files"] == ["2026-05-13_120000_in_window.md"]


# ---------------------------------------------------------------------------
# check_context_budget_trend
# ---------------------------------------------------------------------------

def test_kb_under_warn_is_ok():
    audits = [{"approximate_input_kb": 73}, {"approximate_input_kb": 80}]
    finding = pm.check_context_budget_trend(audits, kb_warn=150, kb_fail=190)
    assert finding.severity == pm.OK


def test_kb_at_warn_warns():
    audits = [{"approximate_input_kb": 150}]
    finding = pm.check_context_budget_trend(audits, kb_warn=150, kb_fail=190)
    assert finding.severity == pm.WARN


def test_kb_at_fail_fails():
    audits = [{"approximate_input_kb": 195}]
    finding = pm.check_context_budget_trend(audits, kb_warn=150, kb_fail=190)
    assert finding.severity == pm.FAIL


def test_kb_no_samples_is_ok():
    finding = pm.check_context_budget_trend([])
    assert finding.severity == pm.OK


def test_kb_uses_latest_for_severity_not_average():
    """One bad audit at the end should flag even if older ones are fine."""
    audits = [
        {"approximate_input_kb": 70},
        {"approximate_input_kb": 80},
        {"approximate_input_kb": 200},
    ]
    finding = pm.check_context_budget_trend(audits, kb_warn=150, kb_fail=190)
    assert finding.severity == pm.FAIL
    assert finding.detail["latest_kb"] == 200


def test_kb_warn_surfaces_heaviest_files():
    """When the latest audit warns/fails, the finding's detail must include
    the actual heavy files driving the budget so the operator knows what to
    cut without grepping audit YAML."""
    audits = [
        {
            "approximate_input_kb": 178,
            "files_read": [
                {"path": "journals/daily/2026-05-14.md", "bytes": 45000},
                {"path": "reports/pre_market/2026-05-14.md", "bytes": 18000},
                {"path": "data/market/2026-05-14/0630.json", "bytes": 18000},
                {"path": "CLAUDE.md", "bytes": 12000},  # > 10 KB threshold
                {"path": "trades/paper/positions.json", "bytes": 500},
            ],
        },
    ]
    finding = pm.check_context_budget_trend(audits, kb_warn=150, kb_fail=190)
    assert finding.severity == pm.WARN
    heavy = finding.detail["heaviest_files"]
    # Files >= 10 KB show up, sub-10KB dropped, sorted by size desc, top 5.
    assert [h["path"] for h in heavy] == [
        "journals/daily/2026-05-14.md",
        "reports/pre_market/2026-05-14.md",
        "data/market/2026-05-14/0630.json",
        "CLAUDE.md",
    ]


def test_kb_ok_omits_heaviest_files():
    """No need to surface heavy files when budget is fine — keep output clean."""
    audits = [
        {
            "approximate_input_kb": 30,
            "files_read": [{"path": "x.md", "bytes": 30000}],
        },
    ]
    finding = pm.check_context_budget_trend(audits, kb_warn=150, kb_fail=190)
    assert finding.severity == pm.OK
    assert "heaviest_files" not in finding.detail


# ---------------------------------------------------------------------------
# parse_audit
# ---------------------------------------------------------------------------

def test_parse_audit_returns_dict(tmp_path):
    path = tmp_path / "2026-05-14_120000_end_of_day_audit.md"
    path.write_text(
        "routine: end_of_day\n"
        "started_at: '2026-05-14T12:00:00+00:00'\n"
        "ended_at: '2026-05-14T12:01:00+00:00'\n"
        "approximate_input_kb: 73\n"
    )
    data = pm.parse_audit(path)
    assert data is not None
    assert data["routine"] == "end_of_day"
    assert data["approximate_input_kb"] == 73


def test_parse_audit_rejects_non_audit_filename(tmp_path):
    path = tmp_path / "2026-05-14_120000_start.md"  # not an audit
    path.write_text("routine: end_of_day\n")
    assert pm.parse_audit(path) is None


# ---------------------------------------------------------------------------
# run_checks / exit_code
# ---------------------------------------------------------------------------

def _state(**overrides):
    defaults = dict(
        trades=[],
        positions={},
        circuit_breaker={
            "state": "FULL", "peak_equity": 100000, "last_observed_equity": 100000,
        },
        audits=[],
        risk_event_files=[],
    )
    defaults.update(overrides)
    return pm.PaperState(**defaults)


def test_run_checks_all_ok_exits_zero():
    report = pm.run_checks(_state(), today=date(2026, 5, 14))
    assert report.exit_code == 0
    assert all(f.severity == pm.OK for f in report.findings)


def test_run_checks_fail_exits_two():
    state = _state(
        trades=[_trade("GLD", "BUY", 34)],
        positions={},  # missing position → FAIL
    )
    report = pm.run_checks(state, today=date(2026, 5, 14))
    assert report.exit_code == 2


def test_run_checks_warn_only_exits_one(tmp_path):
    # context budget at warn threshold but everything else ok
    state = _state(audits=[{"approximate_input_kb": 160}])
    report = pm.run_checks(state, today=date(2026, 5, 14), kb_warn=150, kb_fail=190)
    assert report.exit_code == 1


def test_format_report_includes_all_findings():
    report = pm.run_checks(_state(), today=date(2026, 5, 14))
    out = pm.format_report(report)
    assert "log_positions_reconciliation" in out
    assert "circuit_breaker" in out
    assert "Exit code: 0" in out
