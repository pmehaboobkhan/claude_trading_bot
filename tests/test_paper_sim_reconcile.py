"""Tests for lib.paper_sim.reconcile() — RESET-aware reconciliation.

trades/paper/log.csv is append-only. When sync_alpaca_state.py --reset-fresh-start
runs it appends a watershed row with symbol=_RESET_ / status=RESET. All rows
above that line are stale — the broker side was emptied and positions.json was
overwritten to {}. reconcile() must ignore pre-RESET rows or it surfaces
phantom discrepancies that desensitize the operator to real divergence.

Regression context: the 2026-05-15 09:35 ET market_open run flagged 4 stale
pre-reset OPENs (GLD/GOOGL/XOM/WMT) as discrepancies even though the broker
and positions.json were both legitimately empty post-reset.

Run with: pytest tests/test_paper_sim_reconcile.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import paper_sim  # noqa: E402

HEADER = ",".join(paper_sim.LOG_HEADER) + "\n"


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(paper_sim, "PAPER_DIR", tmp_path)
    monkeypatch.setattr(paper_sim, "LOG_PATH", tmp_path / "log.csv")
    monkeypatch.setattr(paper_sim, "POSITIONS_PATH", tmp_path / "positions.json")
    return tmp_path


def _write_log(tmp_path: Path, rows: list[str]) -> None:
    (tmp_path / "log.csv").write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")


def _write_positions(tmp_path: Path, content: str) -> None:
    (tmp_path / "positions.json").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Pre-reset rows must NOT surface as discrepancies
# ---------------------------------------------------------------------------

def test_reconcile_ignores_pre_reset_opens_when_positions_empty(isolated):
    """The exact 2026-05-15 market_open scenario: 4 pre-reset OPENs, empty
    positions.json — should reconcile cleanly with zero discrepancies."""
    _write_log(isolated, [
        "2026-05-12T20:02:25+00:00,GLD,BUY,34,430.0,decisions/2026-05-12/2002_GLD.json,387,538,OPEN,0,",
        "2026-05-12T20:03:00+00:00,GOOGL,BUY,5,397.91,decisions/2026-05-12/2003_GOOGL.json,358,497,OPEN,0,",
        "2026-05-12T20:04:00+00:00,XOM,BUY,10,110.0,decisions/2026-05-12/2004_XOM.json,99,138,OPEN,0,",
        "2026-05-12T20:05:00+00:00,WMT,BUY,15,85.0,decisions/2026-05-12/2005_WMT.json,77,106,OPEN,0,",
        "2026-05-15T00:31:53+00:00,_RESET_,RESET,0,0,scripts/sync_alpaca_state.py,,,RESET,0,fresh-start",
    ])
    _write_positions(isolated, "{}")

    result = paper_sim.reconcile()

    assert result["open_count"] == 0
    assert result["discrepancies"] == []


def test_reconcile_only_considers_post_reset_rows(isolated):
    """Pre-reset OPENs are dropped; only post-reset rows form 'live' state."""
    _write_log(isolated, [
        "2026-05-12T20:02:25+00:00,GLD,BUY,34,430.0,old.json,387,538,OPEN,0,pre-reset",
        "2026-05-15T00:31:53+00:00,_RESET_,RESET,0,0,scripts/sync_alpaca_state.py,,,RESET,0,fresh-start",
        "2026-05-15T13:35:00+00:00,SPY,BUY,10,500.0,decisions/2026-05-15/1335_SPY.json,450,625,OPEN,0,post-reset",
    ])
    _write_positions(isolated, '{"SPY": {"side": "BUY", "quantity": 10.0, "entry_price": 500.0}}')

    result = paper_sim.reconcile()

    assert result["open_count"] == 1
    assert result["discrepancies"] == []


def test_reconcile_detects_real_post_reset_divergence(isolated):
    """A post-reset OPEN missing from positions.json is a REAL discrepancy."""
    _write_log(isolated, [
        "2026-05-15T00:31:53+00:00,_RESET_,RESET,0,0,scripts/sync_alpaca_state.py,,,RESET,0,fresh-start",
        "2026-05-15T13:35:00+00:00,SPY,BUY,10,500.0,decisions/2026-05-15/1335_SPY.json,450,625,OPEN,0,post-reset",
    ])
    _write_positions(isolated, "{}")

    result = paper_sim.reconcile()

    assert result["open_count"] == 1
    assert any(d["symbol"] == "SPY" for d in result["discrepancies"])


def test_reconcile_no_reset_marker_behaves_as_before(isolated):
    """When no RESET marker exists, the whole log is live — backward-compat."""
    _write_log(isolated, [
        "2026-05-15T13:35:00+00:00,SPY,BUY,10,500.0,decisions/2026-05-15/1335_SPY.json,450,625,OPEN,0,",
    ])
    _write_positions(isolated, '{"SPY": {"side": "BUY", "quantity": 10.0, "entry_price": 500.0}}')

    result = paper_sim.reconcile()

    assert result["open_count"] == 1
    assert result["discrepancies"] == []


def test_reconcile_multiple_resets_uses_latest(isolated):
    """If the log has multiple RESET markers, only the LAST one matters."""
    _write_log(isolated, [
        "2026-05-10T00:00:00+00:00,AAA,BUY,1,100.0,old.json,,,OPEN,0,first-era",
        "2026-05-11T00:00:00+00:00,_RESET_,RESET,0,0,scripts/sync_alpaca_state.py,,,RESET,0,reset-1",
        "2026-05-12T00:00:00+00:00,BBB,BUY,1,100.0,mid.json,,,OPEN,0,middle-era",
        "2026-05-15T00:31:53+00:00,_RESET_,RESET,0,0,scripts/sync_alpaca_state.py,,,RESET,0,reset-2",
        "2026-05-15T13:35:00+00:00,CCC,BUY,1,100.0,new.json,,,OPEN,0,current-era",
    ])
    _write_positions(isolated, '{"CCC": {"side": "BUY", "quantity": 1.0, "entry_price": 100.0}}')

    result = paper_sim.reconcile()

    assert result["open_count"] == 1
    assert result["discrepancies"] == []


def test_reconcile_post_reset_close_clears_position(isolated):
    """A post-reset CLOSE row should remove the OPEN from the live set."""
    _write_log(isolated, [
        "2026-05-15T00:31:53+00:00,_RESET_,RESET,0,0,scripts/sync_alpaca_state.py,,,RESET,0,fresh-start",
        "2026-05-15T13:35:00+00:00,SPY,BUY,10,500.0,decisions/2026-05-15/1335_SPY.json,450,625,OPEN,0,",
        "2026-05-15T15:00:00+00:00,SPY,CLOSE,10,510.0,decisions/2026-05-15/1500_SPY.json,,,CLOSED,100,target",
    ])
    _write_positions(isolated, "{}")

    result = paper_sim.reconcile()

    assert result["open_count"] == 0
    assert result["discrepancies"] == []
