"""Unit tests for lib/phase2_gate.py — the mechanical Phase 2 gate evaluator.

Inputs are pure (dates, commit subject lists, tmp_path file objects) so all
checks run without touching the real repo state.

Run with: pytest tests/test_phase2_gate.py -v
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from lib import phase2_gate as pg


# ---------------------------------------------------------------------------
# calendar helpers
# ---------------------------------------------------------------------------

def test_is_trading_day_weekend():
    assert pg.is_trading_day(date(2026, 5, 16)) is False  # Sat
    assert pg.is_trading_day(date(2026, 5, 17)) is False  # Sun


def test_is_trading_day_weekday():
    assert pg.is_trading_day(date(2026, 5, 11)) is True  # Mon
    assert pg.is_trading_day(date(2026, 5, 15)) is True  # Fri


def test_previous_trading_day_skips_weekend():
    # 2026-05-18 is Mon; previous trading day is Fri 2026-05-15
    assert pg.previous_trading_day(date(2026, 5, 18)) == date(2026, 5, 15)


def test_recent_trading_days_skips_weekends():
    days = pg.recent_trading_days(date(2026, 5, 18), 7)  # Mon
    # Should be Mon, Fri, Thu, Wed, Tue, Mon, Fri
    assert days == [
        date(2026, 5, 18), date(2026, 5, 15), date(2026, 5, 14),
        date(2026, 5, 13), date(2026, 5, 12), date(2026, 5, 11),
        date(2026, 5, 8),
    ]


# ---------------------------------------------------------------------------
# assess_day — happy path
# ---------------------------------------------------------------------------

def _journal(tmp_path: Path, d: date, kb: int = 20) -> Path:
    p = tmp_path / f"{d.isoformat()}.md"
    p.write_text("x" * (kb * 1024), encoding="utf-8")
    return p


def _pm_report(tmp_path: Path, d: date, kb: int = 15) -> Path:
    p = tmp_path / f"pm_{d.isoformat()}.md"
    p.write_text("y" * (kb * 1024), encoding="utf-8")
    return p


def _audit(tmp_path: Path, d: date, routine: str, hhmmss: str = "120000",
           exit_reason: str = "clean") -> Path:
    p = tmp_path / f"{d.isoformat()}_{hhmmss}_{routine}_audit.md"
    p.write_text(
        f"routine: {routine}\n"
        f"started_at: '{d.isoformat()}T12:00:00+00:00'\n"
        f"ended_at: '{d.isoformat()}T12:01:00+00:00'\n"
        f"duration_seconds: 60.0\n"
        f"exit_reason: {exit_reason}\n"
        f"approximate_input_kb: 50\n",
        encoding="utf-8",
    )
    return p


def test_assess_day_clean(tmp_path):
    d = date(2026, 5, 14)
    a = pg.assess_day(
        d,
        today=date(2026, 5, 15),  # next day; d is complete
        commit_subjects=[
            "pre-market: research report 2026-05-14 (7 candidates)",
            "eod: journal + perf 2026-05-14 (PnL +$842, 0 trades)",
        ],
        pre_market_report_path=_pm_report(tmp_path, d),
        journal_path=_journal(tmp_path, d, kb=20),
        risk_event_filenames=[],
        audit_paths=[
            _audit(tmp_path, d, "pre_market", "063000"),
            _audit(tmp_path, d, "end_of_day", "163000"),
        ],
    )
    assert a.status == pg.CLEAN
    assert a.pre_market_commit is True
    assert a.eod_commit is True
    assert a.halt_files == []
    assert a.audits_clean is True


def test_assess_day_partial_missing_eod(tmp_path):
    d = date(2026, 5, 12)
    a = pg.assess_day(
        d,
        today=date(2026, 5, 15),
        commit_subjects=["pre-market: research report 2026-05-12 (5 candidates)"],
        pre_market_report_path=_pm_report(tmp_path, d),
        journal_path=_journal(tmp_path, d, kb=10),
        risk_event_filenames=[],
        audit_paths=[],
    )
    assert a.status == pg.PARTIAL
    assert "eod commit" in a.notes[0]


def test_assess_day_halted(tmp_path):
    d = date(2026, 5, 14)
    a = pg.assess_day(
        d,
        today=date(2026, 5, 15),
        commit_subjects=[
            "pre-market: research report 2026-05-14",
            "eod: journal + perf 2026-05-14",
        ],
        pre_market_report_path=_pm_report(tmp_path, d),
        journal_path=_journal(tmp_path, d, kb=20),
        risk_event_filenames=["2026-05-14_120000_routine_halted.md"],
        audit_paths=[],
    )
    assert a.status == pg.HALTED
    assert a.halt_files == ["2026-05-14_120000_routine_halted.md"]


def test_assess_day_incomplete_today(tmp_path):
    """Today shows INCOMPLETE if EOD hasn't fired yet."""
    today = date(2026, 5, 15)
    a = pg.assess_day(
        today,
        today=today,
        commit_subjects=["pre-market: research report 2026-05-15 (3 candidates)"],
        pre_market_report_path=_pm_report(tmp_path, today),
        journal_path=_journal(tmp_path, today, kb=8),
        risk_event_filenames=[],
        audit_paths=[],
    )
    assert a.status == pg.INCOMPLETE


def test_assess_day_not_trading_weekend(tmp_path):
    a = pg.assess_day(
        date(2026, 5, 16),  # Sat
        today=date(2026, 5, 18),
        commit_subjects=[],
        pre_market_report_path=None,
        journal_path=None,
        risk_event_filenames=[],
        audit_paths=[],
    )
    assert a.status == pg.NOT_TRADING


def test_assess_day_journal_too_small_is_partial(tmp_path):
    """A pre_market + EOD that produced a stub journal isn't a clean day."""
    d = date(2026, 5, 14)
    a = pg.assess_day(
        d,
        today=date(2026, 5, 15),
        commit_subjects=[
            "pre-market: research report 2026-05-14",
            "eod: journal + perf 2026-05-14",
        ],
        pre_market_report_path=_pm_report(tmp_path, d),
        # Below JOURNAL_MIN_BYTES (2 KB)
        journal_path=_journal(tmp_path, d, kb=1),
        risk_event_filenames=[],
        audit_paths=[],
    )
    assert a.status == pg.PARTIAL
    assert "journal too small" in a.notes[0]


def test_assess_day_dirty_audit_is_partial(tmp_path):
    """An audit with exit_reason: error/halted should fail the day."""
    d = date(2026, 5, 14)
    a = pg.assess_day(
        d,
        today=date(2026, 5, 15),
        commit_subjects=[
            "pre-market: research report 2026-05-14",
            "eod: journal + perf 2026-05-14",
        ],
        pre_market_report_path=_pm_report(tmp_path, d),
        journal_path=_journal(tmp_path, d, kb=20),
        risk_event_filenames=[],
        audit_paths=[_audit(tmp_path, d, "end_of_day", exit_reason="error")],
    )
    assert a.status == pg.PARTIAL
    assert "audit" in a.notes[0].lower()


# ---------------------------------------------------------------------------
# halt detection
# ---------------------------------------------------------------------------

def test_circuit_breaker_risk_event_is_not_a_halt():
    """A circuit_breaker.md is informational, not a halt — must not fail the day."""
    halts = pg._find_halt_files(
        ["2026-05-14_133948_circuit_breaker.md"],
        date(2026, 5, 14),
    )
    assert halts == []


def test_halted_risk_event_is_detected():
    halts = pg._find_halt_files(
        [
            "2026-05-14_120000_routine_halted.md",
            "2026-05-14_133948_circuit_breaker.md",
        ],
        date(2026, 5, 14),
    )
    assert halts == ["2026-05-14_120000_routine_halted.md"]


def test_halt_from_other_date_ignored():
    halts = pg._find_halt_files(
        ["2026-05-13_120000_routine_halted.md"],
        date(2026, 5, 14),
    )
    assert halts == []


# ---------------------------------------------------------------------------
# GateResult — aggregate logic
# ---------------------------------------------------------------------------

def _clean_day(d: date) -> pg.DayAssessment:
    return pg.DayAssessment(
        date=d, status=pg.CLEAN,
        pre_market_commit=True, eod_commit=True,
        pre_market_report_bytes=15000, journal_bytes=20000,
        halt_files=[], audits_clean=True, audits_seen=["pre_market", "end_of_day"],
    )


def _weekend(d: date) -> pg.DayAssessment:
    return pg.DayAssessment(
        date=d, status=pg.NOT_TRADING,
        pre_market_commit=False, eod_commit=False,
        pre_market_report_bytes=0, journal_bytes=0,
        halt_files=[], audits_clean=True, audits_seen=[],
    )


def _partial_day(d: date) -> pg.DayAssessment:
    return pg.DayAssessment(
        date=d, status=pg.PARTIAL,
        pre_market_commit=True, eod_commit=False,
        pre_market_report_bytes=15000, journal_bytes=0,
        halt_files=[], audits_clean=True, audits_seen=[],
    )


def test_gate_passes_with_five_consecutive_clean():
    # newest first
    days = [_clean_day(date(2026, 5, 14 - i)) for i in range(5)]
    result = pg.GateResult(today=date(2026, 5, 15), assessments=days)
    assert result.consecutive_clean_from_most_recent_complete == 5
    assert result.passes


def test_gate_fails_with_four_clean_then_partial():
    days = [
        _clean_day(date(2026, 5, 14)),
        _clean_day(date(2026, 5, 13)),
        _clean_day(date(2026, 5, 12)),
        _clean_day(date(2026, 5, 11)),
        _partial_day(date(2026, 5, 8)),
    ]
    result = pg.GateResult(today=date(2026, 5, 15), assessments=days)
    assert result.consecutive_clean_from_most_recent_complete == 4
    assert not result.passes


def test_gate_skips_incomplete_today_and_continues_count():
    """If today is INCOMPLETE the run continues with yesterday."""
    incomplete_today = pg.DayAssessment(
        date=date(2026, 5, 15), status=pg.INCOMPLETE,
        pre_market_commit=True, eod_commit=False,
        pre_market_report_bytes=15000, journal_bytes=8000,
        halt_files=[], audits_clean=True, audits_seen=["pre_market"],
    )
    days = [
        incomplete_today,
        _clean_day(date(2026, 5, 14)),
        _clean_day(date(2026, 5, 13)),
        _clean_day(date(2026, 5, 12)),
    ]
    result = pg.GateResult(today=date(2026, 5, 15), assessments=days)
    # 3 consecutive clean from the most-recent complete day
    assert result.consecutive_clean_from_most_recent_complete == 3
    assert not result.passes


def test_gate_skips_weekends_in_run_count():
    """A weekend in the middle of an assessment window shouldn't break the run."""
    days = [
        _clean_day(date(2026, 5, 18)),  # Mon
        _weekend(date(2026, 5, 17)),    # Sun
        _weekend(date(2026, 5, 16)),    # Sat
        _clean_day(date(2026, 5, 15)),  # Fri
        _clean_day(date(2026, 5, 14)),  # Thu
    ]
    result = pg.GateResult(today=date(2026, 5, 18), assessments=days)
    # 3 consecutive clean trading days (skipping weekends)
    assert result.consecutive_clean_from_most_recent_complete == 3
