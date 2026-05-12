"""Routine-run audit logs — observability for context/cost drift.

Each routine writes one audit file at end of run to
`logs/routine_runs/<YYYY-MM-DD_HHMMSS>_<routine>_audit.md`. Records what
was read, how many subagent dispatches happened, what was written, and a
rough byte-count proxy for token usage.

We cannot measure actual tokens used from inside the model. The byte-count
of files read is a reasonable proxy: it's the most-controllable axis of
context cost, and trending it over time will surface drift before it
blows up the window.

YAML body — structured, single source of truth. The hook-written
SessionStart/SessionEnd markers (`*_start.md` / `*_end.md`) are unchanged
and remain alongside.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = REPO_ROOT / "logs" / "routine_runs"

VALID_EXIT_REASONS = ("clean", "halted", "error", "noop")
ROUTINE_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class RoutineAudit:
    routine: str                              # pre_market | end_of_day | market_open | ...
    started_at: str                           # ISO 8601 with TZ
    ended_at: str                             # ISO 8601 with TZ
    duration_seconds: float
    exit_reason: str                          # clean | halted | error | noop
    files_read: list[dict] = field(default_factory=list)
    """Each entry: {"path": <str>, "bytes": <int>}. Append-only during the run."""
    subagent_dispatches: dict[str, int] = field(default_factory=dict)
    """Map subagent_name -> call count."""
    artifacts_written: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    """Short SHAs (7 chars)."""
    notes: str = ""

    def __post_init__(self) -> None:
        if not ROUTINE_SLUG_RE.match(self.routine):
            raise ValueError(
                f"routine must be a snake_case slug, got {self.routine!r}"
            )
        if self.exit_reason not in VALID_EXIT_REASONS:
            raise ValueError(
                f"exit_reason must be one of {VALID_EXIT_REASONS}, "
                f"got {self.exit_reason!r}"
            )
        if self.duration_seconds < 0:
            raise ValueError(
                f"duration_seconds must be non-negative, got {self.duration_seconds}"
            )

    @property
    def approximate_input_kb(self) -> int:
        """Proxy for input-token cost: sum of files_read byte sizes / 1024."""
        return sum(e["bytes"] for e in self.files_read) // 1024

    @property
    def total_subagent_dispatches(self) -> int:
        return sum(self.subagent_dispatches.values())


def _ts_to_filename_prefix(iso_ts: str) -> str:
    """Convert ISO timestamp like '2026-05-12T13:30:00Z' to '2026-05-12_133000'."""
    # Be permissive — strip tz suffix and seconds-fraction.
    cleaned = re.sub(r"[+\-]\d\d:?\d\d$|Z$", "", iso_ts)
    cleaned = cleaned.split(".")[0]
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        # Fallback: now in UTC.
        dt = datetime.now(UTC)
    return dt.strftime("%Y-%m-%d_%H%M%S")


def write_audit(audit: RoutineAudit, *, dir_path: Path | None = None) -> Path:
    """Persist the audit log. Filename: <YYYY-MM-DD_HHMMSS>_<routine>_audit.md."""
    target_dir = dir_path or AUDIT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = _ts_to_filename_prefix(audit.started_at)
    target = target_dir / f"{prefix}_{audit.routine}_audit.md"

    payload = {
        "routine": audit.routine,
        "started_at": audit.started_at,
        "ended_at": audit.ended_at,
        "duration_seconds": round(audit.duration_seconds, 2),
        "exit_reason": audit.exit_reason,
        "approximate_input_kb": audit.approximate_input_kb,
        "total_subagent_dispatches": audit.total_subagent_dispatches,
        "subagent_dispatches": audit.subagent_dispatches,
        "files_read": audit.files_read,
        "artifacts_written": audit.artifacts_written,
        "commits": audit.commits,
    }
    if audit.notes:
        payload["notes"] = audit.notes

    target.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return target


def file_record(path: str | Path) -> dict:
    """Build a `files_read` entry from a path on disk. Returns {"path": str, "bytes": int}.

    Convenience for routine code that's accumulating reads — call this with
    the absolute path you just Read, append to audit.files_read.
    """
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    # Store as repo-relative when possible — easier to read in logs.
    try:
        display = str(p.relative_to(REPO_ROOT))
    except ValueError:
        display = str(p)
    return {"path": display, "bytes": size}
