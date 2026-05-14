"""Daily snapshots — context-budget protection for routines.

end_of_day writes a small (~500-byte) snapshot of the day's essential facts
to `memory/daily_snapshots/<YYYY-MM-DD>.md`. Pre-market and intraday routines
read the last few snapshots instead of the full daily journals — same
high-level information, an order of magnitude less context.

Format is markdown with a YAML frontmatter for the parseable bits, narrative
body for the rest. Frontmatter parses with PyYAML; body is left as raw text.

Snapshots are NOT covered by hook #4 (journal immutability) — they live
under memory/, not journals/. That means end_of_day can re-write the same
day's snapshot if it re-runs (e.g. for debugging). Day-N snapshots are
never touched on Day-N+1; they accumulate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = REPO_ROOT / "memory" / "daily_snapshots"


@dataclass
class DailySnapshot:
    """Essential facts at end of one trading day.

    Lists are bounded at the routine level — keep them to ~10 entries max so
    the file stays under 1 KB. Anything longer should be summarized.
    """
    date: str                              # YYYY-MM-DD
    regime: str                            # bullish_trend | range_bound | high_vol | ...
    regime_confidence: str                 # low | medium | high
    circuit_breaker_state: str             # FULL | HALF | OUT
    circuit_breaker_dd_pct: float          # current drawdown from peak (0-100 scale)
    pnl_today_usd: float
    pnl_today_pct: float
    open_positions_count: int
    trades_executed: int
    mode: str                              # PAPER_TRADING | RESEARCH_ONLY | HALTED
    decisions_made: list[str] = field(default_factory=list)
    open_positions: list[str] = field(default_factory=list)
    risk_events: list[str] = field(default_factory=list)
    notable: str = ""
    watch_tomorrow: list[str] = field(default_factory=list)
    spy_above_10mo_sma: bool | None = None  # Optional: today's SPY 10mo-SMA filter state
    vix_close: float | None = None          # Optional: today's VIX close (from broker quote feed)

    def __post_init__(self) -> None:
        if self.regime_confidence not in ("low", "medium", "high"):
            raise ValueError(
                f"regime_confidence must be low/medium/high, got {self.regime_confidence!r}"
            )
        if self.circuit_breaker_state not in ("FULL", "HALF", "OUT"):
            raise ValueError(
                f"circuit_breaker_state must be FULL/HALF/OUT, got {self.circuit_breaker_state!r}"
            )
        if not 0 <= self.circuit_breaker_dd_pct <= 100:
            raise ValueError(
                f"circuit_breaker_dd_pct must be in [0, 100], got {self.circuit_breaker_dd_pct}"
            )
        if self.vix_close is not None and not 0 <= self.vix_close <= 200:
            raise ValueError(
                f"vix_close must be in [0, 200], got {self.vix_close}"
            )


def write_snapshot(snap: DailySnapshot, *, dir_path: Path | None = None) -> Path:
    """Persist a snapshot. Overwrites if the same date already exists."""
    target_dir = dir_path or SNAPSHOT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{snap.date}.md"

    frontmatter = {
        "date": snap.date,
        "regime": snap.regime,
        "regime_confidence": snap.regime_confidence,
        "circuit_breaker_state": snap.circuit_breaker_state,
        "circuit_breaker_dd_pct": snap.circuit_breaker_dd_pct,
        "pnl_today_usd": snap.pnl_today_usd,
        "pnl_today_pct": snap.pnl_today_pct,
        "open_positions_count": snap.open_positions_count,
        "trades_executed": snap.trades_executed,
        "mode": snap.mode,
    }
    if snap.spy_above_10mo_sma is not None:
        frontmatter["spy_above_10mo_sma"] = bool(snap.spy_above_10mo_sma)
    if snap.vix_close is not None:
        frontmatter["vix_close"] = float(snap.vix_close)

    def _bullets(items: list[str], empty: str = "(none)") -> str:
        if not items:
            return f"- {empty}"
        return "\n".join(f"- {i}" for i in items)

    body = "\n".join([
        "---",
        yaml.safe_dump(frontmatter, sort_keys=False, default_flow_style=False).rstrip(),
        "---",
        "",
        "## Decisions made today",
        _bullets(snap.decisions_made),
        "",
        "## Open positions",
        _bullets(snap.open_positions),
        "",
        "## Risk events",
        _bullets(snap.risk_events),
        "",
        "## Notable",
        snap.notable.strip() or "(routine day — nothing notable)",
        "",
        "## Watch tomorrow",
        _bullets(snap.watch_tomorrow, empty="(nothing flagged)"),
        "",
    ])
    target.write_text(body, encoding="utf-8")
    return target


def list_recent(n: int = 5, *, dir_path: Path | None = None) -> list[Path]:
    """Return paths to the N most recent snapshots, newest first."""
    d = dir_path or SNAPSHOT_DIR
    if not d.exists():
        return []
    return sorted(d.glob("*.md"), reverse=True)[:n]


def read_recent_text(n: int = 5, *, dir_path: Path | None = None) -> str:
    """Concatenate the N most recent snapshots as raw text, newest first.

    Suitable for passing to the orchestrator as a single context block —
    typically ~1 KB per snapshot × 5 = ~5 KB total. Compare to ~50 KB for
    5 raw daily journals.
    """
    parts = []
    for p in list_recent(n, dir_path=dir_path):
        parts.append(f"<!-- {p.name} -->\n{p.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def parse_frontmatter(text: str) -> dict:
    """Extract the YAML frontmatter from snapshot text. Returns empty dict
    if no frontmatter is present (defensive — never raises on missing/
    malformed input)."""
    if not text.lstrip().startswith("---"):
        return {}
    body = text.lstrip()[3:]
    end = body.find("\n---")
    if end == -1:
        return {}
    try:
        loaded = yaml.safe_load(body[:end])
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
