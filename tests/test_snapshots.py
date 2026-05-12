"""Unit tests for lib/snapshots.py — daily snapshot read/write/parse.

Run with: pytest tests/test_snapshots.py -v
"""
from __future__ import annotations

import pytest

from lib import snapshots
from lib.snapshots import DailySnapshot, parse_frontmatter, read_recent_text, write_snapshot


def _quiet_snapshot(date: str = "2026-05-12", **overrides) -> DailySnapshot:
    """Helper: produce a snapshot for a calm uneventful day."""
    defaults = dict(
        date=date,
        regime="range_bound",
        regime_confidence="low",
        circuit_breaker_state="FULL",
        circuit_breaker_dd_pct=0.0,
        pnl_today_usd=0.0,
        pnl_today_pct=0.0,
        open_positions_count=0,
        trades_executed=0,
        mode="PAPER_TRADING",
    )
    defaults.update(overrides)
    return DailySnapshot(**defaults)


# ---------------------------------------------------------------------------
# Dataclass invariants
# ---------------------------------------------------------------------------

def test_invalid_regime_confidence_rejected() -> None:
    with pytest.raises(ValueError, match="regime_confidence"):
        _quiet_snapshot(regime_confidence="extremely-confident")


def test_invalid_circuit_breaker_state_rejected() -> None:
    with pytest.raises(ValueError, match="circuit_breaker_state"):
        _quiet_snapshot(circuit_breaker_state="MAYBE")


def test_drawdown_out_of_range_rejected() -> None:
    with pytest.raises(ValueError, match="circuit_breaker_dd_pct"):
        _quiet_snapshot(circuit_breaker_dd_pct=150.0)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def test_write_creates_file_at_expected_path(tmp_path) -> None:
    snap = _quiet_snapshot()
    out = write_snapshot(snap, dir_path=tmp_path)
    assert out == tmp_path / "2026-05-12.md"
    assert out.exists()


def test_write_has_yaml_frontmatter_with_essential_fields(tmp_path) -> None:
    snap = _quiet_snapshot(
        regime="bullish_trend",
        regime_confidence="medium",
        circuit_breaker_state="HALF",
        circuit_breaker_dd_pct=8.5,
        pnl_today_pct=-1.2,
        trades_executed=3,
        mode="PAPER_TRADING",
    )
    out = write_snapshot(snap, dir_path=tmp_path)
    text = out.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    assert fm["regime"] == "bullish_trend"
    assert fm["regime_confidence"] == "medium"
    assert fm["circuit_breaker_state"] == "HALF"
    assert fm["circuit_breaker_dd_pct"] == 8.5
    assert fm["pnl_today_pct"] == -1.2
    assert fm["trades_executed"] == 3


def test_write_renders_empty_lists_as_none_bullet(tmp_path) -> None:
    snap = _quiet_snapshot()
    out = write_snapshot(snap, dir_path=tmp_path)
    text = out.read_text(encoding="utf-8")
    assert "## Decisions made today\n- (none)" in text
    assert "## Open positions\n- (none)" in text
    assert "## Risk events\n- (none)" in text
    assert "## Watch tomorrow\n- (nothing flagged)" in text


def test_write_renders_populated_lists(tmp_path) -> None:
    snap = _quiet_snapshot(
        decisions_made=["GOOGL → PAPER_BUY (large_cap_momentum_top5)",
                        "JNJ → PAPER_BUY (large_cap_momentum_top5)"],
        open_positions=["GOOGL 50 @ 180.50 (entry 178.20, +1.3%)"],
        risk_events=["circuit_breaker FULL→HALF at 8.78% DD"],
        watch_tomorrow=["FOMC minutes 14:00 ET"],
        notable="Tech leadership weakened mid-session; rotation into staples observed.",
    )
    out = write_snapshot(snap, dir_path=tmp_path)
    text = out.read_text(encoding="utf-8")
    assert "GOOGL → PAPER_BUY" in text
    assert "GOOGL 50 @ 180.50" in text
    assert "circuit_breaker FULL→HALF" in text
    assert "FOMC minutes 14:00 ET" in text
    assert "rotation into staples" in text


def test_write_is_idempotent_overwrites_same_date(tmp_path) -> None:
    snap1 = _quiet_snapshot(notable="first version")
    snap2 = _quiet_snapshot(notable="second version")
    write_snapshot(snap1, dir_path=tmp_path)
    out = write_snapshot(snap2, dir_path=tmp_path)
    assert "second version" in out.read_text()
    assert "first version" not in out.read_text()


def test_write_keeps_snapshot_under_1kb_for_typical_day(tmp_path) -> None:
    """Context-budget guarantee: a typical-day snapshot fits in ~1 KB.

    If this test starts failing, somebody added too much to the format. The
    point of snapshots is small-and-cheap context for next-day routines.
    """
    snap = _quiet_snapshot(
        decisions_made=[f"SYM{i} → ENTRY" for i in range(8)],
        open_positions=[f"SYM{i} qty=100" for i in range(5)],
        risk_events=[],
        notable="Range-bound session, no notable activity.",
        watch_tomorrow=["FOMC tomorrow at 14:00 ET"],
    )
    out = write_snapshot(snap, dir_path=tmp_path)
    assert out.stat().st_size < 1024, (
        f"snapshot grew to {out.stat().st_size} bytes — keep it ≤ 1 KB"
    )


# ---------------------------------------------------------------------------
# Read / list_recent / read_recent_text
# ---------------------------------------------------------------------------

def test_list_recent_returns_newest_first(tmp_path) -> None:
    for d in ("2026-05-09", "2026-05-12", "2026-05-10", "2026-05-11"):
        write_snapshot(_quiet_snapshot(date=d), dir_path=tmp_path)
    recent = snapshots.list_recent(n=3, dir_path=tmp_path)
    names = [p.name for p in recent]
    assert names == ["2026-05-12.md", "2026-05-11.md", "2026-05-10.md"]


def test_list_recent_empty_when_dir_missing(tmp_path) -> None:
    assert snapshots.list_recent(dir_path=tmp_path / "missing") == []


def test_read_recent_text_concatenates_with_headers(tmp_path) -> None:
    for d in ("2026-05-11", "2026-05-12"):
        write_snapshot(_quiet_snapshot(date=d), dir_path=tmp_path)
    text = read_recent_text(n=2, dir_path=tmp_path)
    # Newest first.
    assert text.index("2026-05-12.md") < text.index("2026-05-11.md")
    # Both bodies present.
    assert text.count("## Notable") == 2


# ---------------------------------------------------------------------------
# Frontmatter parser — defensive on bad inputs
# ---------------------------------------------------------------------------

def test_parse_frontmatter_returns_empty_on_no_frontmatter() -> None:
    assert parse_frontmatter("just a markdown file") == {}


def test_parse_frontmatter_returns_empty_on_unterminated() -> None:
    assert parse_frontmatter("---\ndate: 2026-05-12\n") == {}


def test_parse_frontmatter_returns_empty_on_non_dict_yaml() -> None:
    # YAML at the top level is a list, not a mapping → not a valid frontmatter.
    assert parse_frontmatter("---\n- one\n- two\n---\nbody") == {}


def test_parse_frontmatter_returns_empty_on_unparseable_yaml() -> None:
    # Unclosed quote — PyYAML raises YAMLError.
    assert parse_frontmatter("---\nfield: \"unclosed\nother: 1\n---\nbody") == {}


def test_parse_frontmatter_parses_types_correctly(tmp_path) -> None:
    snap = _quiet_snapshot(
        circuit_breaker_dd_pct=12.34,
        pnl_today_usd=-1500.50,
        trades_executed=4,
    )
    out = write_snapshot(snap, dir_path=tmp_path)
    fm = parse_frontmatter(out.read_text())
    assert isinstance(fm["circuit_breaker_dd_pct"], float)
    assert isinstance(fm["trades_executed"], int)
    assert fm["pnl_today_usd"] == pytest.approx(-1500.50)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
