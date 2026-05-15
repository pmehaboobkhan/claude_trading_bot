"""Paper-trading sanity checks for the first weeks of live paper operation.

Routine commits show trades land; what we don't get for free is a flag when
the local state quietly drifts:

  - the trade log accumulates BUYs without matching SELLs but positions.json
    silently misses them (a `paper_sim` bug, a partial run, manual edits);
  - circuit_breaker.json has peak_equity below current equity (impossible
    under the state machine — means someone wrote it manually);
  - the context-budget proxy (`approximate_input_kb` in audit logs) starts
    climbing toward the 200 KB advisory cap.

This module computes those checks deterministically. Pure functions on
parsed input — no I/O — so the CLI driver in `scripts/paper_trading_monitor.py`
can mock everything.

Severity levels:
  - OK    : nothing to act on.
  - WARN  : worth a look but not blocking.
  - FAIL  : drift the operator must investigate before the next routine fires.

Aggregate exit code: 0 if all OK; 1 if any WARN; 2 if any FAIL.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from pathlib import Path

import yaml

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

# Audit filename pattern: `<YYYY-MM-DD>_<HHMMSS>_<routine>_audit.md`.
AUDIT_FILENAME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})_\d{6}_(?P<routine>[a-z][a-z0-9_]*)_audit\.md$"
)

# Risk-event filename pattern: `<YYYY-MM-DD>_<HHMMSS>_<kind>.md` (or any .md
# under logs/risk_events/). We just need a date prefix.
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

# Default thresholds. Operator can override via the CLI.
DEFAULT_KB_WARN = 150
DEFAULT_KB_FAIL = 190  # cap is 200; flag just before
DEFAULT_RISK_EVENTS_WARN = 5  # per window
DEFAULT_WINDOW_DAYS = 7


@dataclass(frozen=True)
class Finding:
    """One check result. ``severity`` drives the aggregate exit code."""
    check: str
    severity: str  # OK | WARN | FAIL
    summary: str
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Report:
    findings: list[Finding]
    window_start: date
    window_end: date

    @property
    def exit_code(self) -> int:
        if any(f.severity == FAIL for f in self.findings):
            return 2
        if any(f.severity == WARN for f in self.findings):
            return 1
        return 0


# ---------------------------------------------------------------------------
# Parsers — each takes raw bytes/string and returns plain dicts so the
# checkers below can be unit-tested without touching the filesystem.
# ---------------------------------------------------------------------------

RESET_TOKENS = ("RESET", "MARKER", "_RESET_", "_MARKER_")


def _is_reset_row(row: dict) -> bool:
    """True if a CSV row is a watershed marker rather than a real trade.

    ``scripts/sync_alpaca_state.py`` writes markers with ``symbol=_RESET_``
    and ``status=RESET``. Older convention used ``symbol=RESET``. Be liberal:
    if any of {symbol, side, status} is one of the reset tokens, treat it
    as a marker.
    """
    for field_name in ("symbol", "side", "status"):
        if row.get(field_name, "").strip().upper() in RESET_TOKENS:
            return True
    return False


def parse_trade_log(csv_text: str) -> list[dict]:
    """Parse trades/paper/log.csv, RESET-aware.

    ``trades/paper/log.csv`` is append-only — when ``sync_alpaca_state.py
    --reset-fresh-start`` runs, it doesn't rewrite old rows. Instead it
    appends a single row with ``symbol=_RESET_`` / ``status=RESET``.
    Everything above that line is no longer "live state" — the prior OPEN
    positions were closed at the broker side and ``positions.json`` was
    emptied. The reconciliation check must ignore them.

    Rule: keep only rows AFTER the last reset marker. Marker rows themselves
    are dropped. If there are no markers, the whole log is "live" (the
    pre-reset behaviour).
    """
    rows: list[dict] = list(csv.DictReader(StringIO(csv_text)))
    last_reset_idx = -1
    for i, row in enumerate(rows):
        if _is_reset_row(row):
            last_reset_idx = i
    live = rows[last_reset_idx + 1 :] if last_reset_idx >= 0 else rows
    return [r for r in live if not _is_reset_row(r)]


def parse_positions(json_text: str) -> dict[str, dict]:
    return json.loads(json_text) if json_text.strip() else {}


def parse_circuit_breaker(json_text: str) -> dict:
    return json.loads(json_text) if json_text.strip() else {}


def parse_audit(path: Path) -> dict | None:
    """Best-effort parse of a routine_audit YAML-bodied .md file.

    Returns None if the file doesn't look like an audit (e.g. the hook-written
    *_start.md / *_end.md markers have a different shape).
    """
    if not AUDIT_FILENAME_RE.match(path.name):
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or "routine" not in data:
        return None
    return data


# ---------------------------------------------------------------------------
# Checkers — each returns a single Finding.
# ---------------------------------------------------------------------------

def check_log_positions_reconciliation(
    trades: list[dict], positions: dict[str, dict]
) -> Finding:
    """Net open BUY-SELL per symbol must equal positions.json quantities.

    Closed trades (status != OPEN) and matched BUY/SELL pairs net to zero and
    drop out of the comparison.
    """
    derived: dict[str, float] = {}
    for row in trades:
        if row.get("status") != "OPEN":
            continue
        symbol = row.get("symbol", "")
        side = row.get("side", "").upper()
        try:
            qty = float(row.get("quantity", "0") or "0")
        except ValueError:
            continue
        signed = qty if side == "BUY" else -qty if side == "SELL" else 0.0
        derived[symbol] = derived.get(symbol, 0.0) + signed
    derived = {s: q for s, q in derived.items() if abs(q) > 1e-9}

    actual = {
        s: float(p.get("quantity", p.get("qty", 0)))
        for s, p in positions.items()
    }
    actual = {s: q for s, q in actual.items() if abs(q) > 1e-9}

    only_log = sorted(set(derived) - set(actual))
    only_positions = sorted(set(actual) - set(derived))
    qty_diff = sorted(
        s for s in set(derived) & set(actual)
        if abs(derived[s] - actual[s]) > 1e-6
    )

    if only_log or only_positions or qty_diff:
        return Finding(
            check="log_positions_reconciliation",
            severity=FAIL,
            summary=(
                f"trade log and positions.json disagree: "
                f"only_in_log={only_log} only_in_positions={only_positions} "
                f"qty_mismatch={qty_diff}"
            ),
            detail={
                "only_in_log": only_log,
                "only_in_positions": only_positions,
                "qty_mismatch": [
                    {"symbol": s, "from_log": derived[s], "from_positions": actual[s]}
                    for s in qty_diff
                ],
            },
        )
    return Finding(
        check="log_positions_reconciliation",
        severity=OK,
        summary=f"trade log and positions.json in sync ({len(actual)} open positions)",
    )


def check_circuit_breaker(cb: dict) -> Finding:
    """Sanity-check trades/paper/circuit_breaker.json shape + values.

    Hard rules:
      - state must be FULL | HALF | OUT
      - peak_equity must be >= last_observed_equity (the state machine never
        ratchets peak down).
    """
    if not cb:
        return Finding(
            check="circuit_breaker",
            severity=WARN,
            summary="circuit_breaker.json is missing/empty — first routine since reset?",
        )

    state = cb.get("state")
    peak = cb.get("peak_equity")
    last = cb.get("last_observed_equity")

    if state not in ("FULL", "HALF", "OUT"):
        return Finding(
            check="circuit_breaker",
            severity=FAIL,
            summary=f"unknown circuit-breaker state: {state!r}",
            detail=cb,
        )
    if peak is None or last is None:
        return Finding(
            check="circuit_breaker",
            severity=FAIL,
            summary="circuit_breaker.json missing peak_equity or last_observed_equity",
            detail=cb,
        )
    try:
        peak_f = float(peak)
        last_f = float(last)
    except (TypeError, ValueError):
        return Finding(
            check="circuit_breaker",
            severity=FAIL,
            summary="peak_equity / last_observed_equity not numeric",
            detail=cb,
        )
    if peak_f < last_f - 1e-6:
        return Finding(
            check="circuit_breaker",
            severity=FAIL,
            summary=(
                f"peak_equity {peak_f} below last_observed_equity {last_f} — "
                f"state machine should ratchet peak up only"
            ),
            detail=cb,
        )
    drawdown_pct = 100.0 * (peak_f - last_f) / peak_f if peak_f else 0.0
    return Finding(
        check="circuit_breaker",
        severity=OK,
        summary=(
            f"circuit-breaker {state} (DD {drawdown_pct:.2f}%, peak ${peak_f:,.2f})"
        ),
        detail={
            "state": state,
            "peak_equity": peak_f,
            "last_observed_equity": last_f,
            "drawdown_pct": round(drawdown_pct, 2),
        },
    )


def check_risk_events_in_window(
    event_files: list[Path],
    window_start: date,
    window_end: date,
    *,
    warn_count: int = DEFAULT_RISK_EVENTS_WARN,
) -> Finding:
    """Count `logs/risk_events/*.md` whose date prefix falls in the window.

    Above ``warn_count`` is a WARN, not a FAIL — risk events are meant to fire
    and a flurry of them might be legitimate (e.g. circuit-breaker transitions
    during a real drawdown). The operator should still look.
    """
    in_window: list[str] = []
    for path in event_files:
        m = DATE_PREFIX_RE.match(path.name)
        if not m:
            continue
        try:
            d = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if window_start <= d <= window_end:
            in_window.append(path.name)
    in_window.sort()
    count = len(in_window)
    severity = OK if count == 0 else WARN if count >= warn_count else OK
    return Finding(
        check="risk_events_in_window",
        severity=severity,
        summary=(
            f"{count} risk event(s) in last {(window_end - window_start).days + 1} day(s)"
            f" (warn threshold {warn_count})"
        ),
        detail={"files": in_window},
    )


def check_context_budget_trend(
    audits: list[dict],
    *,
    kb_warn: int = DEFAULT_KB_WARN,
    kb_fail: int = DEFAULT_KB_FAIL,
) -> Finding:
    """Trend `approximate_input_kb` across the audits passed in.

    The latest reading drives the severity; the average is reported for
    context. The intent is to surface drift before the 200 KB advisory cap
    in `risk_limits.yaml > cost_caps` is breached.
    """
    kbs = [int(a["approximate_input_kb"]) for a in audits
           if isinstance(a.get("approximate_input_kb"), (int, float))]
    if not kbs:
        return Finding(
            check="context_budget_trend",
            severity=OK,
            summary="no audit files with approximate_input_kb in window",
        )
    latest = kbs[-1]
    avg = sum(kbs) / len(kbs)
    if latest >= kb_fail:
        sev = FAIL
    elif latest >= kb_warn:
        sev = WARN
    else:
        sev = OK
    return Finding(
        check="context_budget_trend",
        severity=sev,
        summary=(
            f"latest approximate_input_kb={latest} (avg {avg:.1f} over "
            f"{len(kbs)} audit(s); warn {kb_warn} / fail {kb_fail})"
        ),
        detail={
            "latest_kb": latest,
            "avg_kb": round(avg, 1),
            "n_samples": len(kbs),
            "thresholds": {"warn": kb_warn, "fail": kb_fail},
        },
    )


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

@dataclass
class PaperState:
    """Plain-data input bundle for ``run_checks`` — keeps the function pure
    and unit-testable. The CLI driver wires this up from real files."""
    trades: list[dict]
    positions: dict[str, dict]
    circuit_breaker: dict
    audits: list[dict]
    risk_event_files: list[Path]


def run_checks(
    state: PaperState,
    *,
    today: date | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    kb_warn: int = DEFAULT_KB_WARN,
    kb_fail: int = DEFAULT_KB_FAIL,
    risk_events_warn: int = DEFAULT_RISK_EVENTS_WARN,
) -> Report:
    if today is None:
        today = datetime.now(UTC).date()
    window_start = today - timedelta(days=window_days - 1)
    findings = [
        check_log_positions_reconciliation(state.trades, state.positions),
        check_circuit_breaker(state.circuit_breaker),
        check_risk_events_in_window(
            state.risk_event_files, window_start, today,
            warn_count=risk_events_warn,
        ),
        check_context_budget_trend(state.audits, kb_warn=kb_warn, kb_fail=kb_fail),
    ]
    return Report(findings=findings, window_start=window_start, window_end=today)


def format_report(report: Report) -> str:
    """Human-readable rendering of a Report."""
    lines = [
        f"Paper-trading monitor — {report.window_start} → {report.window_end}",
        "=" * 60,
    ]
    for f in report.findings:
        lines.append(f"[{f.severity:4}] {f.check}: {f.summary}")
    lines.append("")
    lines.append(f"Exit code: {report.exit_code}")
    return "\n".join(lines)
