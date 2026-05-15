"""Unit tests for lib/symbol_history.py — per-symbol decision-history compression.

Tests use synthetic markdown closely mirroring the real format in
`decisions/by_symbol/<SYM>.md`. The compression operation must be:
  - deterministic (same input → same output, byte for byte),
  - idempotent (re-running on already-compressed content extends or no-ops),
  - non-destructive on the header (`## Cumulative stats` block at top untouched).

Run with: pytest tests/test_symbol_history.py -v
"""
from __future__ import annotations

import textwrap

from lib import symbol_history
from lib.symbol_history import (
    COMPRESSED_BEGIN,
    COMPRESSED_END,
    compress,
    parse_history,
)


HEADER = textwrap.dedent("""\
    # SPY — Per-Symbol Decision Log

    **Cumulative stats (updated 2026-05-14 EOD):**

    - Open paper positions: 0
    - Realized PnL: +$1,000.00
    - Win rate: 50% (2/4)
    """)


def _make_entry(date: str, action: str, pnl: str | None = None) -> str:
    body_lines = [
        f"- Decision file: `decisions/{date}/2000_SPY.json`",
        f"- Routine: end_of_day_{date}, mode PAPER_TRADING",
    ]
    if pnl is not None:
        body_lines.append(f"- Realized PnL: {pnl}")
    return f"## {date} — {action}\n\n" + "\n".join(body_lines) + "\n"


def _make_doc(*entries: str) -> str:
    return HEADER + "\n" + "\n".join(entries)


def test_under_threshold_is_no_op() -> None:
    """≤ keep_recent entries → text unchanged."""
    entries = [_make_entry(f"2026-05-{d:02d}", "PAPER_BUY")
               for d in range(1, 11)]  # 10 entries
    doc = _make_doc(*entries)

    out = compress(doc, keep_recent=50)

    assert out == doc


def test_compression_triggers_above_threshold() -> None:
    """75 entries with keep_recent=50 → 25 collapsed, 50 kept verbatim."""
    entries = []
    for i in range(75):
        # spread across two months so we can verify date_range
        month = 4 if i < 30 else 5
        day = (i % 30) + 1
        entries.append(_make_entry(f"2026-{month:02d}-{day:02d}", "PAPER_BUY"))
    doc = _make_doc(*entries)

    out = compress(doc, keep_recent=50, archive_link="decisions/by_symbol/archive/SPY_pre.md")

    assert COMPRESSED_BEGIN in out
    assert COMPRESSED_END in out
    assert "Entries collapsed: 25" in out
    # First 25 entries (oldest) should NOT appear as ## headings anymore.
    first_25_dates = [e for e in entries[:25] if "PAPER_BUY" in e]
    for e in first_25_dates[:5]:
        date_line = e.split("\n")[0]
        # The exact date line as a heading should be gone (replaced by summary).
        # The date may still appear inside the date_range summary line.
        assert out.count(date_line) == 0, f"old heading still present: {date_line}"
    # Last entry's heading should still be present verbatim.
    last_heading = entries[-1].split("\n")[0]
    assert last_heading in out


def test_header_block_untouched() -> None:
    """The cumulative-stats header block must be byte-identical after compression."""
    entries = [_make_entry(f"2026-05-{(i % 28) + 1:02d}", "PAPER_BUY")
               for i in range(60)]
    doc = _make_doc(*entries)

    out = compress(doc, keep_recent=50)

    # The header (everything before the first `##` heading) must be present
    # at the start of `out`.
    assert out.startswith(HEADER.rstrip("\n"))


def test_realized_pnl_summed_correctly() -> None:
    """Realized PnL lines in collapsed entries are summed; sign respected."""
    entries = []
    # 60 entries: first 10 have PnL, rest don't (so 10 get aggregated)
    for i in range(60):
        if i < 5:
            entries.append(_make_entry(f"2026-04-{i + 1:02d}", "PAPER_CLOSE",
                                       pnl=f"+${(i + 1) * 100}.00"))
        elif i < 10:
            entries.append(_make_entry(f"2026-04-{i + 1:02d}", "PAPER_CLOSE",
                                       pnl=f"-${(i - 4) * 10}.00"))
        else:
            entries.append(_make_entry(f"2026-05-{(i - 9):02d}", "PAPER_BUY"))
    doc = _make_doc(*entries)

    out = compress(doc, keep_recent=50)

    # First 10 entries collapsed: PnL sum = (100+200+300+400+500) + (-10-20-30-40-50) = 1500 - 150 = 1350
    assert "Realized PnL on closed trades: +$1,350.00 (across 10 closed-trade entries)" in out


def test_no_pnl_lines_yields_na() -> None:
    """No collapsed entry has a PnL line → summary reports n/a."""
    entries = [_make_entry(f"2026-05-{(i % 28) + 1:02d}", "PAPER_BUY")
               for i in range(60)]
    doc = _make_doc(*entries)

    out = compress(doc, keep_recent=50)

    assert "Realized PnL on closed trades: n/a (no parsable PnL lines)" in out


def test_idempotent_no_new_entries() -> None:
    """Compress then compress again → second call is a no-op."""
    entries = [_make_entry(f"2026-05-{(i % 28) + 1:02d}", "PAPER_BUY")
               for i in range(60)]
    doc = _make_doc(*entries)

    once = compress(doc, keep_recent=50)
    twice = compress(once, keep_recent=50)

    assert once == twice


def test_idempotent_extends_when_more_entries_added() -> None:
    """After compress, add 20 more entries → recompress collapses the next 20."""
    initial_entries = [_make_entry(f"2026-04-{(i % 28) + 1:02d}", "PAPER_BUY")
                       for i in range(60)]
    doc = _make_doc(*initial_entries)
    first = compress(doc, keep_recent=50,
                     archive_link="decisions/by_symbol/archive/SPY_pre_v1.md")

    # First compress: 10 collapsed, 50 kept. Add 10 new entries.
    new_entries = [_make_entry(f"2026-05-{i + 1:02d}", "PAPER_BUY")
                   for i in range(10)]
    extended = first + "\n" + "\n".join(new_entries)

    second = compress(extended, keep_recent=50,
                      archive_link="decisions/by_symbol/archive/SPY_pre_v2.md")

    # Now total entries (kept + new) = 50 + 10 = 60; need to collapse 10 more.
    # Merged compressed total: 10 + 10 = 20.
    assert "Entries collapsed: 20" in second


def test_parse_history_roundtrip_below_threshold() -> None:
    """parse_history's parts reassemble (modulo whitespace normalization) when
    no compression triggers."""
    entries = [_make_entry(f"2026-05-{i + 1:02d}", "PAPER_BUY")
               for i in range(5)]
    doc = _make_doc(*entries)

    parsed = parse_history(doc)

    assert parsed.header.strip().startswith("# SPY")
    assert parsed.compressed[0] == ""
    assert len(parsed.entries) == 5
    assert parsed.entries[0].date == "2026-05-01"
    assert parsed.entries[-1].date == "2026-05-05"


def test_categorize_picks_first_matching_keyword() -> None:
    """Heading contains both PAPER_CLOSE and NO_TRADE → PAPER_CLOSE wins
    (precedence order in ACTION_KEYWORDS)."""
    h = "## 2026-05-13 — PAPER_CLOSE (pre_close, overnight, NO_TRADE override)"
    assert symbol_history._categorize(h) == "PAPER_CLOSE"


def test_bold_cumulative_stats_not_misread_as_entry() -> None:
    """Lines starting with `**Cumulative stats` are NOT entry headings."""
    doc = HEADER + "\n## 2026-05-12 — PAPER_BUY\n\n- body\n\n" + \
        "**Cumulative stats (updated 2026-05-12 EOD):**\n- foo\n\n" + \
        "## 2026-05-13 — PAPER_CLOSE\n\n- body 2\n"

    parsed = parse_history(doc)

    assert len(parsed.entries) == 2
    # The bold-cumulative-stats line is part of entry-1's body, not a header.
    assert "Cumulative stats" in parsed.entries[0].body


def test_pnl_parser_handles_formatting_variants() -> None:
    """The Realized-PnL regex handles bold/sign/comma variations."""
    cases = [
        ("Realized PnL: $0.00", 0.0),
        ("Realized PnL: +$412.18", 412.18),
        ("Realized PnL: -$45.20", -45.20),
        ("Realized PnL: **+$618.90** (+10.13% on $5,957.14)", 618.90),
        ("Realized PnL: +$1,234.56", 1234.56),
    ]
    for line, expected in cases:
        body = f"- Routine: foo\n- {line}\n- more bullets"
        got = symbol_history._parse_realized_pnl(body)
        assert got == expected, f"{line!r} → {got!r}, expected {expected!r}"

    # Missing PnL line → None
    assert symbol_history._parse_realized_pnl("- Routine: foo\n- other bullet") is None


def test_archive_link_appears_in_summary() -> None:
    entries = [_make_entry(f"2026-05-{(i % 28) + 1:02d}", "PAPER_BUY")
               for i in range(60)]
    doc = _make_doc(*entries)
    link = "decisions/by_symbol/archive/SPY_pre_2026-05-15.md"

    out = compress(doc, keep_recent=50, archive_link=link)

    assert f"See `{link}` for full history." in out


def test_compress_keep_recent_zero_collapses_everything() -> None:
    entries = [_make_entry(f"2026-05-{i + 1:02d}", "PAPER_BUY")
               for i in range(5)]
    doc = _make_doc(*entries)

    out = compress(doc, keep_recent=0,
                   archive_link="decisions/by_symbol/archive/SPY_pre_x.md")

    # All 5 entries collapsed; no `## YYYY-MM-DD —` entry headings remain in the
    # rebuilt output (summary heading "## Summary before" is fine).
    for i in range(5):
        assert f"## 2026-05-{i + 1:02d} — PAPER_BUY" not in out
    assert "Entries collapsed: 5" in out


def test_negative_keep_recent_raises() -> None:
    import pytest as _pytest
    with _pytest.raises(ValueError, match="keep_recent must be >= 0"):
        compress("# x\n", keep_recent=-1)


def test_archive_path_for_helper() -> None:
    from pathlib import Path
    p = symbol_history.archive_path_for("GLD", "2026-05-12", Path("decisions/by_symbol"))
    assert p == Path("decisions/by_symbol/archive/GLD_pre_2026-05-12.md")
