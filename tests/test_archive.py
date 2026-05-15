"""Unit tests for lib/archive.py — routine-log auto-archive.

Date is injected (not derived from `datetime.now()`) so these tests are
deterministic. The pattern mirrors tests/test_portfolio_risk.py.

Run with: pytest tests/test_archive.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib import archive
from lib.archive import ArchiveResult, archive_old_logs


def _touch(p: Path, body: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_within_window_is_untouched(tmp_path: Path) -> None:
    """Files within keep_days remain in place; no archive dir is created."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "2026-05-13_063015_pre_market_start.md")
    _touch(log_dir / "2026-05-14_163505_end_of_day_end.md")

    result = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)

    assert result.archived == 0
    assert result.skipped_recent == 2
    assert (log_dir / "2026-05-13_063015_pre_market_start.md").exists()
    assert (log_dir / "2026-05-14_163505_end_of_day_end.md").exists()
    assert not (log_dir / "archive").exists()


def test_outside_window_moves_to_year_month(tmp_path: Path) -> None:
    """Files older than keep_days move under archive/<year>/<month>/."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "2026-03-15_063015_pre_market_start.md")
    _touch(log_dir / "2026-04-01_163505_end_of_day_end.md")
    _touch(log_dir / "2026-05-13_063015_pre_market_start.md")  # within window

    result = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)

    assert result.archived == 2
    assert result.skipped_recent == 1
    assert not (log_dir / "2026-03-15_063015_pre_market_start.md").exists()
    assert (log_dir / "archive" / "2026" / "03"
            / "2026-03-15_063015_pre_market_start.md").exists()
    assert (log_dir / "archive" / "2026" / "04"
            / "2026-04-01_163505_end_of_day_end.md").exists()
    assert (log_dir / "2026-05-13_063015_pre_market_start.md").exists()


def test_already_archived_files_not_reprocessed(tmp_path: Path) -> None:
    """Files inside the archive subtree are left alone even if old."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "archive" / "2025" / "12"
           / "2025-12-01_063015_pre_market_start.md")
    # Note: the loop only sees top-level files; the archive subdir is skipped
    # at the directory level, so this is more of a defensive check.

    result = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)

    assert result.archived == 0
    assert (log_dir / "archive" / "2025" / "12"
            / "2025-12-01_063015_pre_market_start.md").exists()


def test_invalid_filename_raises(tmp_path: Path) -> None:
    """We want to know about filename drift; don't silently skip."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "not-a-routine-log.md")

    with pytest.raises(ValueError, match="unrecognized log filename"):
        archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)


def test_dry_run_touches_nothing(tmp_path: Path) -> None:
    """Dry-run reports counts but does not move any files."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "2026-03-15_063015_pre_market_start.md")

    result = archive_old_logs(
        log_dir, today_iso="2026-05-14", keep_days=30, dry_run=True
    )

    assert result.archived == 1
    assert result.dry_run is True
    # File still in original location
    assert (log_dir / "2026-03-15_063015_pre_market_start.md").exists()
    assert not (log_dir / "archive").exists()


def test_non_md_files_are_tolerated(tmp_path: Path) -> None:
    """Stray files like .gitkeep don't raise; they're just skipped."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / ".gitkeep", body="")
    _touch(log_dir / "2026-03-15_063015_pre_market_start.md")

    result = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)

    assert result.archived == 1
    assert (log_dir / ".gitkeep").exists()


def test_missing_log_dir_returns_empty_result(tmp_path: Path) -> None:
    """A non-existent log dir is not an error (routine may run pre-creation)."""
    result = archive_old_logs(
        tmp_path / "does_not_exist", today_iso="2026-05-14"
    )
    assert result.archived == 0
    assert result.skipped_recent == 0


def test_negative_keep_days_raises(tmp_path: Path) -> None:
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    with pytest.raises(ValueError, match="keep_days must be >= 0"):
        archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=-1)


def test_idempotent_rerun(tmp_path: Path) -> None:
    """A second call after archival is a no-op."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "2026-03-15_063015_pre_market_start.md")

    first = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)
    assert first.archived == 1

    second = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)
    assert second.archived == 0
    assert second.skipped_recent == 0


def test_boundary_exact_keep_days(tmp_path: Path) -> None:
    """A file exactly keep_days old is kept (not archived)."""
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "2026-04-14_063015_pre_market_start.md")  # exactly 30 days old

    result = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=30)

    assert result.archived == 0
    assert result.skipped_recent == 1


def test_keep_days_zero_archives_everything_before_today(tmp_path: Path) -> None:
    log_dir = tmp_path / "routine_runs"
    log_dir.mkdir()
    _touch(log_dir / "2026-05-13_063015_pre_market_start.md")
    _touch(log_dir / "2026-05-14_063015_pre_market_start.md")  # today

    result = archive_old_logs(log_dir, today_iso="2026-05-14", keep_days=0)

    assert result.archived == 1
    assert (log_dir / "2026-05-14_063015_pre_market_start.md").exists()


def test_parse_filename_date_helper() -> None:
    """Direct check on the private filename parser."""
    assert archive._parse_filename_date(
        "2026-05-14_163505_end_of_day_end.md"
    ) == __import__("datetime").date(2026, 5, 14)
    assert archive._parse_filename_date("garbage.md") is None
    assert archive._parse_filename_date("2026-13-99_000000_x.md") is None  # invalid date
