"""Auto-archive old routine-run logs.

`logs/routine_runs/` accumulates one or two files per routine run. After a few
weeks the directory has hundreds of files and slows grep walks + balloons
context loads. This module moves files older than N days into
`logs/routine_runs/archive/<year>/<month>/`, keyed on the date encoded in the
filename (mtime is unreliable across git clones and worktrees).

Filename convention enforced by the routines:
    <YYYY-MM-DD>_<HHMMSS>_<routine>_<phase>.md
e.g. `2026-04-01_063015_pre_market_start.md`.

The function is pure-ish — `archive_old_logs` only touches the filesystem
when `dry_run=False`. It is idempotent: re-runs on the same directory after
an archive pass are no-ops.

The `today_iso` parameter is injected (not derived from `datetime.now()`) so
the same code is exercised in tests and in the end_of_day routine. Callers
typically pass `date.today().isoformat()`.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

FILENAME_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_\d{6}_.+\.md$")
ARCHIVE_DIRNAME = "archive"


@dataclass
class ArchiveResult:
    archived: int = 0
    skipped_recent: int = 0
    skipped_already_archived: int = 0
    moved_paths: list[Path] = field(default_factory=list)
    dry_run: bool = False


def _parse_filename_date(name: str) -> date | None:
    """Return the calendar date encoded in the filename, or None if unparseable."""
    m = FILENAME_DATE_RE.match(name)
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def archive_old_logs(
    log_dir: Path,
    *,
    today_iso: str,
    keep_days: int = 30,
    dry_run: bool = False,
) -> ArchiveResult:
    """Move files older than `keep_days` from `log_dir/` into
    `log_dir/archive/<year>/<month>/`.

    Files already inside the archive subtree are left alone. Filenames that
    don't match the date-prefixed convention raise `ValueError` — we want to
    know about drift, not silently skip them.

    Args:
      log_dir:    Directory to scan, e.g. `logs/routine_runs/`.
      today_iso:  Reference date in `YYYY-MM-DD` form. A file with embedded
                  date `d` is archived when `(today - d).days > keep_days`.
      keep_days:  Files within this window are kept in place.
      dry_run:    If True, do not touch the filesystem; just report counts.

    Returns:
      ArchiveResult with counts and (when not dry_run) the new paths.
    """
    if keep_days < 0:
        raise ValueError(f"keep_days must be >= 0, got {keep_days}")
    if not log_dir.exists():
        return ArchiveResult(dry_run=dry_run)
    if not log_dir.is_dir():
        raise ValueError(f"{log_dir} is not a directory")

    today = date.fromisoformat(today_iso)
    archive_root = log_dir / ARCHIVE_DIRNAME
    result = ArchiveResult(dry_run=dry_run)

    for entry in sorted(log_dir.iterdir()):
        if entry.is_dir():
            # Skip the archive subtree (and any other subdirs).
            continue
        if not entry.name.endswith(".md"):
            # Tolerate non-md files (e.g. .gitkeep) silently.
            continue

        # Robustness: if the file is somehow nested under archive/, skip it.
        try:
            entry.relative_to(archive_root)
            result.skipped_already_archived += 1
            continue
        except ValueError:
            pass

        file_date = _parse_filename_date(entry.name)
        if file_date is None:
            raise ValueError(
                f"unrecognized log filename: {entry.name} — expected "
                f"YYYY-MM-DD_HHMMSS_<routine>_<phase>.md"
            )

        age_days = (today - file_date).days
        if age_days <= keep_days:
            result.skipped_recent += 1
            continue

        # Destination: archive/<year>/<month>/<filename>
        dest_dir = archive_root / f"{file_date.year:04d}" / f"{file_date.month:02d}"
        dest = dest_dir / entry.name

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry), str(dest))

        result.archived += 1
        result.moved_paths.append(dest)

    return result
