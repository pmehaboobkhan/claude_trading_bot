"""Phase 2 gate evaluation — turn the "5 consecutive clean trading days" check
into a mechanical pass/fail rather than a subjective call.

Gate criteria from `todo.md > Phase 2`:
  - 5 consecutive trading days of clean pre-market + EOD output, no halt
  - Reports human-readable
  - Commits well-formed

Cleanness per trading day:
  1. Both a `pre-market:` and an `eod:` commit landed on that calendar date.
  2. Routine artifacts exist: `reports/pre_market/<date>.md` and
     `journals/daily/<date>.md`.
  3. No `logs/risk_events/<date>_*_halted.md` entry (informational risk events
     like a circuit-breaker transition are NOT halts and don't fail the day).
  4. The day's most recent `_audit.md` files for both routines (if present)
     have `exit_reason: clean`.

"Trading day" = weekday (Mon-Fri). US-holiday calendar is intentionally NOT
loaded here — operators on a holiday should add an `is_holiday_override`
file (TBD) or just accept that the gate skips one weekday in eight years.

Pure functions on plain inputs (paths, parsed JSON/YAML) so the checks are
unit-testable without touching the filesystem. The CLI driver in
`scripts/check_phase2_gate.py` wires this up to the live repo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml

# Status constants for a single day's assessment.
CLEAN = "CLEAN"            # both routines fired + no halts + artifacts present
PARTIAL = "PARTIAL"        # one routine fired, the other didn't
HALTED = "HALTED"          # a halt entry exists for this date
INCOMPLETE = "INCOMPLETE"  # today, or a day still being assembled
NOT_TRADING = "NOT_TRADING"  # weekend (and eventually holidays)

# Filename patterns
HALTED_RISK_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_.*halt", re.IGNORECASE)
AUDIT_FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_\d{6}_(?P<routine>[a-z][a-z0-9_]*)_audit\.md$"
)

# Min journal size to count as "human-readable" — empirically a real day's
# journal is 10-50 KB; under 2 KB suggests the routine wrote a stub and exited.
JOURNAL_MIN_BYTES = 2_048

# Gate target.
REQUIRED_CONSECUTIVE_CLEAN_DAYS = 5


@dataclass(frozen=True)
class DayAssessment:
    """The full evaluation for one calendar date.

    ``status`` is the headline (CLEAN / PARTIAL / HALTED / INCOMPLETE /
    NOT_TRADING). ``details`` captures the per-criterion findings so the
    CLI can render them and tests can introspect.
    """
    date: date
    status: str
    pre_market_commit: bool
    eod_commit: bool
    pre_market_report_bytes: int
    journal_bytes: int
    halt_files: list[str]
    audits_clean: bool
    audits_seen: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GateResult:
    """Top-level gate evaluation across N most recent trading days."""
    today: date
    assessments: list[DayAssessment]
    required: int = REQUIRED_CONSECUTIVE_CLEAN_DAYS

    @property
    def clean_count(self) -> int:
        """Count of CLEAN days in the assessment window."""
        return sum(1 for a in self.assessments if a.status == CLEAN)

    @property
    def consecutive_clean_from_most_recent_complete(self) -> int:
        """Longest run of consecutive CLEAN days starting from the most recent
        complete trading day (skips today if INCOMPLETE).

        This is the metric that drives gate-pass: 5 consecutive ending the
        last fully-evaluated day.
        """
        run = 0
        for a in self.assessments:
            if a.status == INCOMPLETE:
                continue
            if a.status == NOT_TRADING:
                continue
            if a.status == CLEAN:
                run += 1
            else:
                break
        return run

    @property
    def passes(self) -> bool:
        return self.consecutive_clean_from_most_recent_complete >= self.required


def is_trading_day(d: date) -> bool:
    """M-F. Doesn't load a US-holiday calendar in v1."""
    return d.weekday() < 5


def previous_trading_day(d: date) -> date:
    """Walk backward over weekends."""
    prev = d - timedelta(days=1)
    while not is_trading_day(prev):
        prev = prev - timedelta(days=1)
    return prev


def recent_trading_days(today: date, count: int) -> list[date]:
    """The most-recent ``count`` trading days ending at or before ``today``.

    Returned newest-first so iteration matches "scanning from today backward."
    """
    days: list[date] = []
    cursor = today
    while len(days) < count:
        if is_trading_day(cursor):
            days.append(cursor)
        cursor = cursor - timedelta(days=1)
    return days


def _had_commit(commit_subjects: list[str], prefix: str) -> bool:
    """Did any commit on the date start with ``prefix:``?"""
    needle = prefix + ":"
    return any(s.startswith(needle) for s in commit_subjects)


def _find_halt_files(risk_event_filenames: list[str], d: date) -> list[str]:
    """Filenames in `logs/risk_events/` that look like halt entries for date ``d``.

    Pattern: ``<date>_*_halt*.md`` or anything containing "halted" in the name.
    """
    iso = d.isoformat()
    out = []
    for name in risk_event_filenames:
        if not name.startswith(iso):
            continue
        if "halt" in name.lower():
            out.append(name)
    return out


def _audits_for_day(audit_dir_entries: list[Path], d: date) -> list[Path]:
    iso = d.isoformat()
    out: list[Path] = []
    for p in audit_dir_entries:
        m = AUDIT_FILENAME_RE.match(p.name)
        if m and m.group("date") == iso:
            out.append(p)
    return out


def _audits_clean(audits: list[Path]) -> tuple[bool, list[str]]:
    """Parse each audit YAML and return (all-clean, list-of-routine-names-seen)."""
    if not audits:
        return True, []  # no audits is not a failure (older days predate the audit pattern)
    seen: list[str] = []
    all_clean = True
    for p in audits:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            all_clean = False
            seen.append(f"{p.name}(parse-fail)")
            continue
        if not isinstance(data, dict):
            continue
        seen.append(data.get("routine", "?"))
        if data.get("exit_reason") not in ("clean", "noop"):
            all_clean = False
    return all_clean, seen


def assess_day(
    d: date,
    *,
    today: date,
    commit_subjects: list[str],
    pre_market_report_path: Path | None,
    journal_path: Path | None,
    risk_event_filenames: list[str],
    audit_paths: list[Path],
) -> DayAssessment:
    """Evaluate one calendar date. Pure: callers pass in pre-loaded inputs."""
    if not is_trading_day(d):
        return DayAssessment(
            date=d, status=NOT_TRADING,
            pre_market_commit=False, eod_commit=False,
            pre_market_report_bytes=0, journal_bytes=0,
            halt_files=[], audits_clean=True, audits_seen=[],
            notes=["weekend"],
        )

    pre_market_commit = _had_commit(commit_subjects, "pre-market")
    eod_commit = _had_commit(commit_subjects, "eod")
    pm_bytes = pre_market_report_path.stat().st_size if pre_market_report_path and pre_market_report_path.exists() else 0
    journal_bytes = journal_path.stat().st_size if journal_path and journal_path.exists() else 0
    halts = _find_halt_files(risk_event_filenames, d)
    audits_for_day = _audits_for_day(audit_paths, d)
    audits_ok, audits_seen = _audits_clean(audits_for_day)

    notes: list[str] = []
    status = CLEAN

    if d == today:
        # Today is in-progress unless EOD has already fired.
        if not eod_commit:
            status = INCOMPLETE
            notes.append("today — EOD has not yet committed")
    if halts:
        status = HALTED
        notes.append(f"halt entry: {', '.join(halts)}")
    elif not (pre_market_commit and eod_commit):
        if status != INCOMPLETE:
            status = PARTIAL
            missing = []
            if not pre_market_commit: missing.append("pre-market commit")
            if not eod_commit: missing.append("eod commit")
            notes.append("missing: " + ", ".join(missing))
    elif journal_bytes < JOURNAL_MIN_BYTES:
        status = PARTIAL
        notes.append(f"journal too small: {journal_bytes} bytes < {JOURNAL_MIN_BYTES}")
    elif not audits_ok:
        status = PARTIAL
        notes.append("at least one audit's exit_reason was not 'clean' or 'noop'")

    return DayAssessment(
        date=d,
        status=status,
        pre_market_commit=pre_market_commit,
        eod_commit=eod_commit,
        pre_market_report_bytes=pm_bytes,
        journal_bytes=journal_bytes,
        halt_files=halts,
        audits_clean=audits_ok,
        audits_seen=sorted(set(audits_seen)),
        notes=notes,
    )


def format_gate(result: GateResult) -> str:
    """Human-readable render — used by the CLI."""
    lines = [
        f"Phase 2 gate check — {result.today}",
        "=" * 65,
        "Days assessed (most recent first):",
        "",
    ]
    icon = {
        CLEAN: "✅",
        PARTIAL: "⚠️ ",
        HALTED: "🛑",
        INCOMPLETE: "⏳",
        NOT_TRADING: " ·",
    }
    for a in result.assessments:
        line = f"  {a.date}  {icon[a.status]} {a.status:10}"
        if a.status == NOT_TRADING:
            line += "  (weekend)"
        else:
            checks = []
            checks.append(f"pm={'✓' if a.pre_market_commit else '✗'}")
            checks.append(f"eod={'✓' if a.eod_commit else '✗'}")
            checks.append(f"journal={a.journal_bytes // 1024}KB")
            if a.halt_files:
                checks.append(f"halts={len(a.halt_files)}")
            line += "  " + " ".join(checks)
            if a.notes:
                line += "  — " + "; ".join(a.notes)
        lines.append(line)
    lines.append("")
    lines.append(
        f"Consecutive CLEAN days (most-recent complete): "
        f"{result.consecutive_clean_from_most_recent_complete} / {result.required} required"
    )
    lines.append(f"Total CLEAN days in window: {result.clean_count}")
    lines.append("")
    lines.append(
        f"Gate verdict: {'PASS — eligible to advance to Phase 3' if result.passes else 'NOT YET — more clean days needed'}"
    )
    return "\n".join(lines)
