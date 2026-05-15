"""Run paper-trading sanity checks against the live repo state.

Wraps ``lib.paper_monitor`` with filesystem I/O. Reads:
  - trades/paper/log.csv
  - trades/paper/positions.json
  - trades/paper/circuit_breaker.json
  - logs/routine_runs/<...>_audit.md (last N days)
  - logs/risk_events/*.md (last N days)

Outputs a human-readable report (or JSON with ``--json``) and exits:
  0 — all checks OK
  1 — one or more WARN (worth a look)
  2 — one or more FAIL (operator investigation required)

Usage:
    python3 scripts/paper_trading_monitor.py            # daily check
    python3 scripts/paper_trading_monitor.py --days 7   # custom window
    python3 scripts/paper_trading_monitor.py --json     # machine output
    python3 scripts/paper_trading_monitor.py --report-only  # always exit 0
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import paper_monitor as pm  # noqa: E402

TRADES_DIR = REPO_ROOT / "trades" / "paper"
ROUTINE_RUNS_DIR = REPO_ROOT / "logs" / "routine_runs"
RISK_EVENTS_DIR = REPO_ROOT / "logs" / "risk_events"


def _load_state(window_days: int, today: date) -> pm.PaperState:
    """Read live repo files into a PaperState."""
    log_path = TRADES_DIR / "log.csv"
    positions_path = TRADES_DIR / "positions.json"
    cb_path = TRADES_DIR / "circuit_breaker.json"

    trades = pm.parse_trade_log(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    positions = pm.parse_positions(positions_path.read_text(encoding="utf-8")) if positions_path.exists() else {}
    cb = pm.parse_circuit_breaker(cb_path.read_text(encoding="utf-8")) if cb_path.exists() else {}

    window_start = today - timedelta(days=window_days - 1)

    audits: list[dict] = []
    if ROUTINE_RUNS_DIR.is_dir():
        for path in sorted(ROUTINE_RUNS_DIR.iterdir()):
            if not path.is_file():
                continue
            audit = pm.parse_audit(path)
            if audit is None:
                continue
            audit_date = _audit_date(audit)
            if audit_date is None or audit_date < window_start or audit_date > today:
                continue
            audits.append(audit)

    risk_event_files: list[Path] = []
    if RISK_EVENTS_DIR.is_dir():
        risk_event_files = sorted(p for p in RISK_EVENTS_DIR.iterdir() if p.is_file())

    return pm.PaperState(
        trades=trades,
        positions=positions,
        circuit_breaker=cb,
        audits=audits,
        risk_event_files=risk_event_files,
    )


def _audit_date(audit: dict) -> date | None:
    """Pull the date out of an audit's started_at ISO timestamp."""
    started = audit.get("started_at", "")
    if not isinstance(started, str) or len(started) < 10:
        return None
    try:
        return date.fromisoformat(started[:10])
    except ValueError:
        return None


def _report_to_dict(report: pm.Report) -> dict:
    return {
        "window_start": report.window_start.isoformat(),
        "window_end": report.window_end.isoformat(),
        "exit_code": report.exit_code,
        "findings": [
            {
                "check": f.check,
                "severity": f.severity,
                "summary": f.summary,
                "detail": f.detail,
            }
            for f in report.findings
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days",
        type=int,
        default=pm.DEFAULT_WINDOW_DAYS,
        help=f"trailing window in days for audits + risk events (default {pm.DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--kb-warn",
        type=int,
        default=pm.DEFAULT_KB_WARN,
        help=f"approximate_input_kb warn threshold (default {pm.DEFAULT_KB_WARN})",
    )
    parser.add_argument(
        "--kb-fail",
        type=int,
        default=pm.DEFAULT_KB_FAIL,
        help=f"approximate_input_kb fail threshold (default {pm.DEFAULT_KB_FAIL})",
    )
    parser.add_argument(
        "--risk-events-warn",
        type=int,
        default=pm.DEFAULT_RISK_EVENTS_WARN,
        help=f"risk-event count threshold (default {pm.DEFAULT_RISK_EVENTS_WARN})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON report instead of human-readable",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="always exit 0 regardless of severity (useful for cron logging)",
    )
    args = parser.parse_args(argv)

    today = datetime.now(UTC).date()
    state = _load_state(args.days, today)
    report = pm.run_checks(
        state,
        today=today,
        window_days=args.days,
        kb_warn=args.kb_warn,
        kb_fail=args.kb_fail,
        risk_events_warn=args.risk_events_warn,
    )

    if args.json:
        print(json.dumps(_report_to_dict(report), indent=2))
    else:
        print(pm.format_report(report))

    return 0 if args.report_only else report.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
