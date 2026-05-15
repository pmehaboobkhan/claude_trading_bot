#!/usr/bin/env python3
"""CLI wrapper around `lib.archive.archive_old_logs`.

Intended to be called from the end_of_day routine (idempotent — safe to run
on every routine, no-ops when there's nothing old enough to move).

Usage:
    python3 scripts/archive_routine_logs.py
    python3 scripts/archive_routine_logs.py --keep-days 30
    python3 scripts/archive_routine_logs.py --dry-run
    python3 scripts/archive_routine_logs.py --log-dir logs/routine_runs
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import archive  # noqa: E402

DEFAULT_LOG_DIR = REPO_ROOT / "logs" / "routine_runs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-dir", type=Path, default=DEFAULT_LOG_DIR,
        help=f"Directory of routine-run logs (default: {DEFAULT_LOG_DIR})",
    )
    parser.add_argument(
        "--keep-days", type=int, default=30,
        help="Files within this many days of today are kept in place (default: 30).",
    )
    parser.add_argument(
        "--today", type=str, default=date.today().isoformat(),
        help="Reference date in YYYY-MM-DD (default: today). Injectable for tests.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would move without touching the filesystem.",
    )
    args = parser.parse_args(argv)

    try:
        result = archive.archive_old_logs(
            args.log_dir,
            today_iso=args.today,
            keep_days=args.keep_days,
            dry_run=args.dry_run,
        )
    except ValueError as e:
        print(f"[archive] ERROR: {e}", file=sys.stderr)
        return 2

    verb = "would archive" if args.dry_run else "archived"
    print(
        f"[archive] {verb}: {result.archived} files | "
        f"kept (recent): {result.skipped_recent} | "
        f"already-archived: {result.skipped_already_archived}"
    )
    if result.moved_paths:
        for p in result.moved_paths[:5]:
            print(f"  → {p.relative_to(REPO_ROOT)}")
        if len(result.moved_paths) > 5:
            print(f"  ... and {len(result.moved_paths) - 5} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
