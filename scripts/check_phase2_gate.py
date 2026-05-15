"""Evaluate the Phase 2 → Phase 3 gate against the live repo.

Reads commits via ``git log``, journal + pre-market report files from the
working tree, halt entries from ``logs/risk_events/``, and audit YAML from
``logs/routine_runs/``. Renders a per-day assessment and a top-line verdict.

Exit codes:
  0 — gate passes (≥ 5 consecutive clean trading days)
  1 — gate not yet passed (more days needed, or a recent day failed)

Usage:
    python3 scripts/check_phase2_gate.py              # check last 5 trading days
    python3 scripts/check_phase2_gate.py --days 10    # wider window
    python3 scripts/check_phase2_gate.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import phase2_gate as pg  # noqa: E402

JOURNALS_DIR = REPO_ROOT / "journals" / "daily"
PM_REPORTS_DIR = REPO_ROOT / "reports" / "pre_market"
RISK_EVENTS_DIR = REPO_ROOT / "logs" / "risk_events"
ROUTINE_RUNS_DIR = REPO_ROOT / "logs" / "routine_runs"


def _git_commit_subjects_for_date(d: date) -> list[str]:
    """All commit subjects with `committer-date in [date, date+1)`.

    Uses committer date (not author date) so commits that landed on date D
    show up here regardless of when they were originally authored.
    """
    next_day = d + timedelta(days=1)
    cmd = [
        "git", "log",
        f"--since={d.isoformat()} 00:00",
        f"--until={next_day.isoformat()} 00:00",
        "--pretty=format:%s",
    ]
    try:
        out = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as exc:
        print(f"[gate] git log failed: {exc.stderr}", file=sys.stderr)
        return []
    return [line for line in out.stdout.splitlines() if line.strip()]


def _risk_event_filenames() -> list[str]:
    if not RISK_EVENTS_DIR.is_dir():
        return []
    return [p.name for p in RISK_EVENTS_DIR.iterdir() if p.is_file()]


def _audit_paths() -> list[Path]:
    if not ROUTINE_RUNS_DIR.is_dir():
        return []
    return [p for p in ROUTINE_RUNS_DIR.iterdir() if p.is_file()]


def evaluate(today: date, window_days: int) -> pg.GateResult:
    """Build the GateResult from the live filesystem + git."""
    days_to_assess = pg.recent_trading_days(today, window_days)
    # Pre-load filesystem-level inputs once
    risk_events = _risk_event_filenames()
    audits = _audit_paths()

    assessments: list[pg.DayAssessment] = []
    for d in days_to_assess:
        commits = _git_commit_subjects_for_date(d)
        pm_path = PM_REPORTS_DIR / f"{d.isoformat()}.md"
        journal_path = JOURNALS_DIR / f"{d.isoformat()}.md"
        a = pg.assess_day(
            d,
            today=today,
            commit_subjects=commits,
            pre_market_report_path=pm_path if pm_path.exists() else None,
            journal_path=journal_path if journal_path.exists() else None,
            risk_event_filenames=risk_events,
            audit_paths=audits,
        )
        assessments.append(a)

    return pg.GateResult(today=today, assessments=assessments)


def _gate_to_dict(result: pg.GateResult) -> dict:
    return {
        "today": result.today.isoformat(),
        "consecutive_clean": result.consecutive_clean_from_most_recent_complete,
        "required": result.required,
        "clean_count": result.clean_count,
        "passes": result.passes,
        "assessments": [
            {
                "date": a.date.isoformat(),
                "status": a.status,
                "pre_market_commit": a.pre_market_commit,
                "eod_commit": a.eod_commit,
                "pre_market_report_bytes": a.pre_market_report_bytes,
                "journal_bytes": a.journal_bytes,
                "halt_files": a.halt_files,
                "audits_clean": a.audits_clean,
                "audits_seen": a.audits_seen,
                "notes": a.notes,
            }
            for a in result.assessments
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days", type=int, default=pg.REQUIRED_CONSECUTIVE_CLEAN_DAYS,
        help="number of most-recent trading days to assess (default 5)",
    )
    parser.add_argument(
        "--today", default=None,
        help="override 'today' as YYYY-MM-DD (default: actual today UTC)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    if args.today:
        today = date.fromisoformat(args.today)
    else:
        today = datetime.now(UTC).date()

    if args.days < pg.REQUIRED_CONSECUTIVE_CLEAN_DAYS:
        print(
            f"[gate] warning: --days={args.days} is less than the required "
            f"window {pg.REQUIRED_CONSECUTIVE_CLEAN_DAYS}; gate will likely "
            f"never pass without seeing enough history",
            file=sys.stderr,
        )

    result = evaluate(today, args.days)
    if args.json:
        print(json.dumps(_gate_to_dict(result), indent=2))
    else:
        print(pg.format_gate(result))

    return 0 if result.passes else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
