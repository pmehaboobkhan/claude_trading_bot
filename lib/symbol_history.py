"""Per-symbol decision-history compression.

`decisions/by_symbol/<SYM>.md` is an append-only timeline. After a symbol has
been active for a few months it accumulates dozens of `## YYYY-MM-DD — ACTION`
entries. Performance Review reads these files on every weekly review; without
compression the read load grows unbounded.

This module collapses the older entries into a single `## Summary before <date>`
block, leaving the most recent `keep_recent` entries verbatim. Idempotent —
re-running on already-compressed content is a no-op or extends the existing
summary if more entries have aged out.

The append-only hook (#12) enforces row-level immutability on the live file.
This module is invoked by the Performance Review agent, which is the single
authorized writer of these files. The compress operation is structured as a
**rewrite to a known-shape header section + verbatim tail**, mirroring the
existing STATS-block rewrite pattern.

File format (canonical):

    # <SYM> — Per-Symbol Decision Log

    **Cumulative stats (updated <date> EOD):**
    - <bullets>

    <!-- COMPRESSED:BEGIN -->          (optional; present when compression has run)
    ## Summary before <date>
    - Entries collapsed: <N> (<first_date> → <last_date>)
    - PAPER_BUY: <n> | PAPER_SELL: <n> | PAPER_CLOSE: <n> | NO_TRADE: <n> | OTHER: <n>
    - Realized PnL on closed trades: <±$X.XX> (across <N> closed-trade entries)
    - See `decisions/by_symbol/archive/<SYM>_pre_<date>.md` for full history.
    <!-- COMPRESSED:END -->

    ## <date> — ACTION (...)
    - <bullets>
    ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Heading line: `## YYYY-MM-DD — anything`. Use a strict regex so bold lines
# like `**Cumulative stats (updated 2026-05-13 EOD):**` are NOT misread as
# timeline entries — those start with `**`, not `##`.
ENTRY_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b(?:\s+—\s+(.*))?$")

# Bracketed action token in the entry heading. Best-effort: scan the heading
# text for these keywords and categorize.
ACTION_KEYWORDS = (
    ("PAPER_BUY", "PAPER_BUY"),
    ("PAPER_SELL", "PAPER_SELL"),
    ("PAPER_CLOSE", "PAPER_CLOSE"),
    ("NO_TRADE", "NO_TRADE"),
)

# Lines like `- Realized PnL: **+$618.90** (+10.13% on $5,957.14 cost basis).`
# or `- Realized PnL: $0.00` or `- Realized PnL: +$412.18`.
# Capture the signed dollar amount; ignore the percent and cost-basis figures.
REALIZED_PNL_RE = re.compile(
    r"Realized PnL[:\s\*]*([+\-]?)\s*\$([+\-]?)([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)

COMPRESSED_BEGIN = "<!-- COMPRESSED:BEGIN -->"
COMPRESSED_END = "<!-- COMPRESSED:END -->"


@dataclass
class Entry:
    date: str       # YYYY-MM-DD
    heading: str    # full first line, e.g. "## 2026-05-12 — PAPER_BUY (...)"
    body: str       # everything between this heading and the next (or EOF),
                    # NOT including the trailing blank line before the next heading


@dataclass
class CompressedSummary:
    entries_collapsed: int
    date_range: tuple[str, str]              # (first_date, last_date)
    paper_buys: int = 0
    paper_sells: int = 0
    paper_closes: int = 0
    no_trades: int = 0
    other: int = 0
    realized_pnl_usd: float | None = None    # sum across parsable PnL lines
    realized_pnl_count: int = 0              # how many entries contributed
    archive_link: str = ""                   # markdown link string


@dataclass
class ParsedHistory:
    header: str                              # everything before the first `##` heading
    compressed: tuple[str, CompressedSummary | None] = ("", None)
    # When `compressed[0]` is non-empty, it's the raw text of the existing
    # `<!-- COMPRESSED:BEGIN -->...<!-- COMPRESSED:END -->` block (including
    # the markers and any surrounding blank lines). `compressed[1]` is the
    # parsed summary, or None if the block couldn't be re-parsed (in which
    # case `compress()` treats it as opaque and preserves it).
    entries: list[Entry] = field(default_factory=list)


def parse_history(text: str) -> ParsedHistory:
    """Split the file into header, optional existing compressed block, and
    the ordered list of timeline entries.

    The function is purely structural — it does not validate that dates are
    monotone or that entry bodies look sensible. Callers can trust that
    concatenating `header + compressed_text + "\\n".join(e.full_text for e
    in entries)` reproduces the input (modulo trailing-newline normalization).
    """
    lines = text.split("\n")
    n = len(lines)
    i = 0

    # Phase 1: collect header lines until either the first compressed marker
    # or the first timeline heading.
    header_lines: list[str] = []
    while i < n:
        if lines[i].strip() == COMPRESSED_BEGIN:
            break
        if ENTRY_HEADING_RE.match(lines[i]):
            break
        header_lines.append(lines[i])
        i += 1

    header = "\n".join(header_lines)

    # Phase 2: optional compressed block.
    compressed_text = ""
    compressed_summary: CompressedSummary | None = None
    if i < n and lines[i].strip() == COMPRESSED_BEGIN:
        start = i
        while i < n and lines[i].strip() != COMPRESSED_END:
            i += 1
        if i < n:  # found END
            i += 1  # consume the END line
        compressed_text = "\n".join(lines[start:i])
        compressed_summary = _try_parse_compressed_summary(compressed_text)

    # Phase 3: timeline entries.
    entries: list[Entry] = []
    current_heading: str | None = None
    current_date: str | None = None
    current_body_lines: list[str] = []

    def flush() -> None:
        if current_heading is not None and current_date is not None:
            entries.append(Entry(
                date=current_date,
                heading=current_heading,
                body="\n".join(current_body_lines).rstrip("\n"),
            ))

    while i < n:
        m = ENTRY_HEADING_RE.match(lines[i])
        if m:
            flush()
            current_heading = lines[i]
            current_date = m.group(1)
            current_body_lines = []
        else:
            if current_heading is None:
                # Stray content between header/compressed-block and first
                # timeline entry. Append to header rather than dropping.
                header = header + "\n" + lines[i] if header else lines[i]
            else:
                current_body_lines.append(lines[i])
        i += 1
    flush()

    return ParsedHistory(
        header=header,
        compressed=(compressed_text, compressed_summary),
        entries=entries,
    )


def _try_parse_compressed_summary(block: str) -> CompressedSummary | None:
    """Best-effort re-parse of an existing compressed block. Returns None if
    the shape doesn't match — caller preserves the block verbatim."""
    m_entries = re.search(r"Entries collapsed:\s*(\d+)\s+\((\d{4}-\d{2}-\d{2})\s*→\s*(\d{4}-\d{2}-\d{2})\)", block)
    if not m_entries:
        return None

    def _grab(key: str) -> int:
        m = re.search(rf"{key}:\s*(\d+)", block)
        return int(m.group(1)) if m else 0

    pnl_match = re.search(
        r"Realized PnL on closed trades:\s*([+\-]?)\$([\d,]+(?:\.\d+)?)\s*\(across\s*(\d+)\s*closed-trade entries\)",
        block,
    )
    pnl: float | None = None
    pnl_count = 0
    if pnl_match:
        sign = -1 if pnl_match.group(1) == "-" else 1
        pnl = sign * float(pnl_match.group(2).replace(",", ""))
        pnl_count = int(pnl_match.group(3))

    archive_match = re.search(r"See `([^`]+)` for full history", block)

    return CompressedSummary(
        entries_collapsed=int(m_entries.group(1)),
        date_range=(m_entries.group(2), m_entries.group(3)),
        paper_buys=_grab("PAPER_BUY"),
        paper_sells=_grab("PAPER_SELL"),
        paper_closes=_grab("PAPER_CLOSE"),
        no_trades=_grab("NO_TRADE"),
        other=_grab("OTHER"),
        realized_pnl_usd=pnl,
        realized_pnl_count=pnl_count,
        archive_link=archive_match.group(1) if archive_match else "",
    )


def _categorize(heading: str) -> str:
    """Bucket an entry by keyword presence in its heading. Returns one of
    PAPER_BUY, PAPER_SELL, PAPER_CLOSE, NO_TRADE, OTHER.

    Precedence is the order in ACTION_KEYWORDS: a heading like
    `## 2026-05-13 — PAPER_CLOSE (pre_close, no_trade override)` is
    categorized as PAPER_CLOSE, not NO_TRADE.
    """
    upper = heading.upper()
    for keyword, bucket in ACTION_KEYWORDS:
        if keyword in upper:
            return bucket
    return "OTHER"


def _parse_realized_pnl(body: str) -> float | None:
    """Extract the first Realized PnL value from the entry body, or None if absent.

    Handles patterns like:
      - Realized PnL: $0.00
      - Realized PnL: +$412.18
      - Realized PnL: **+$618.90** (+10.13% on $5,957.14 cost basis).
      - Realized PnL: -$45.20
    """
    m = REALIZED_PNL_RE.search(body)
    if not m:
        return None
    sign_outer = m.group(1)
    sign_inner = m.group(2)
    raw_value = m.group(3).replace(",", "")
    try:
        value = float(raw_value)
    except ValueError:
        return None
    if sign_outer == "-" or sign_inner == "-":
        value = -value
    return value


def _summarize(entries: list[Entry], previous: CompressedSummary | None,
               archive_link: str) -> CompressedSummary:
    """Aggregate `entries` (the ones being collapsed) into a CompressedSummary,
    merging with `previous` if there's already a compressed block."""
    buckets = {"PAPER_BUY": 0, "PAPER_SELL": 0, "PAPER_CLOSE": 0,
               "NO_TRADE": 0, "OTHER": 0}
    pnl_sum = 0.0
    pnl_count = 0
    for e in entries:
        buckets[_categorize(e.heading)] += 1
        v = _parse_realized_pnl(e.body)
        if v is not None:
            pnl_sum += v
            pnl_count += 1

    if previous is not None:
        # Merge previously-compressed counts and the prior PnL block.
        for k, prev_val in [
            ("PAPER_BUY", previous.paper_buys),
            ("PAPER_SELL", previous.paper_sells),
            ("PAPER_CLOSE", previous.paper_closes),
            ("NO_TRADE", previous.no_trades),
            ("OTHER", previous.other),
        ]:
            buckets[k] += prev_val
        if previous.realized_pnl_usd is not None:
            pnl_sum += previous.realized_pnl_usd
            pnl_count += previous.realized_pnl_count
        first_date = min(previous.date_range[0], entries[0].date) if entries else previous.date_range[0]
        last_date = max(previous.date_range[1], entries[-1].date) if entries else previous.date_range[1]
        merged_total = previous.entries_collapsed + len(entries)
    else:
        first_date = entries[0].date
        last_date = entries[-1].date
        merged_total = len(entries)

    realized_pnl: float | None = pnl_sum if pnl_count > 0 else None

    return CompressedSummary(
        entries_collapsed=merged_total,
        date_range=(first_date, last_date),
        paper_buys=buckets["PAPER_BUY"],
        paper_sells=buckets["PAPER_SELL"],
        paper_closes=buckets["PAPER_CLOSE"],
        no_trades=buckets["NO_TRADE"],
        other=buckets["OTHER"],
        realized_pnl_usd=realized_pnl,
        realized_pnl_count=pnl_count,
        archive_link=archive_link,
    )


def _format_compressed_block(summary: CompressedSummary, before_date: str) -> str:
    if summary.realized_pnl_usd is None:
        pnl_line = "- Realized PnL on closed trades: n/a (no parsable PnL lines)"
    else:
        sign = "+" if summary.realized_pnl_usd >= 0 else "-"
        pnl_line = (
            f"- Realized PnL on closed trades: {sign}${abs(summary.realized_pnl_usd):,.2f} "
            f"(across {summary.realized_pnl_count} closed-trade entries)"
        )

    counts_line = (
        f"- PAPER_BUY: {summary.paper_buys} | "
        f"PAPER_SELL: {summary.paper_sells} | "
        f"PAPER_CLOSE: {summary.paper_closes} | "
        f"NO_TRADE: {summary.no_trades} | "
        f"OTHER: {summary.other}"
    )

    archive_line = (
        f"- See `{summary.archive_link}` for full history."
        if summary.archive_link
        else "- Full pre-compression history was not archived (compress called without archive_link)."
    )

    return "\n".join([
        COMPRESSED_BEGIN,
        f"## Summary before {before_date}",
        "",
        f"- Entries collapsed: {summary.entries_collapsed} "
        f"({summary.date_range[0]} → {summary.date_range[1]})",
        counts_line,
        pnl_line,
        archive_line,
        COMPRESSED_END,
    ])


def compress(
    text: str,
    *,
    keep_recent: int = 50,
    archive_link: str = "",
) -> str:
    """If the timeline holds more than `keep_recent` entries, collapse the
    oldest excess into a `<!-- COMPRESSED:BEGIN -->...<!-- COMPRESSED:END -->`
    block placed between the header and the first kept entry.

    Args:
      text: full markdown content of `decisions/by_symbol/<SYM>.md`.
      keep_recent: how many of the most recent timeline entries to keep
        verbatim. Default 50 per plan.md.
      archive_link: optional relative path to the archive copy of the
        pre-compression file, e.g. `decisions/by_symbol/archive/GLD_pre_2026-05-12.md`.
        Recorded in the summary block so callers can recover the full
        history if needed. Empty string is permitted (caller is responsible
        for warning the operator if they skip archival).

    Returns:
      Possibly-modified text. Trailing newline preserved if present in input.
    """
    if keep_recent < 0:
        raise ValueError(f"keep_recent must be >= 0, got {keep_recent}")

    parsed = parse_history(text)
    total = len(parsed.entries)
    # Account for entries already inside a prior compressed block — those
    # don't count toward the "keep_recent" budget because they're already
    # compressed. We only compress more if the *live* timeline exceeds the
    # budget.
    if total <= keep_recent:
        return text

    excess = total - keep_recent
    to_collapse = parsed.entries[:excess]
    to_keep = parsed.entries[excess:]

    summary = _summarize(
        to_collapse,
        previous=parsed.compressed[1],
        archive_link=archive_link or (parsed.compressed[1].archive_link
                                      if parsed.compressed[1] else ""),
    )
    # `before_date` labels the summary block. With keep_recent=0 we collapse
    # everything; use "(all)" sentinel rather than indexing into an empty list.
    before_date = to_keep[0].date if to_keep else "(all)"

    compressed_block = _format_compressed_block(summary, before_date)
    rebuilt = _reassemble(parsed.header, compressed_block, to_keep)

    # Preserve a trailing newline if the original had one.
    if text.endswith("\n") and not rebuilt.endswith("\n"):
        rebuilt = rebuilt + "\n"
    return rebuilt


def _reassemble(header: str, compressed_block: str, entries: list[Entry]) -> str:
    """Stitch parts back into a single markdown document."""
    parts: list[str] = []
    if header:
        parts.append(header.rstrip("\n"))
        parts.append("")  # blank line between header and compressed block

    parts.append(compressed_block)
    parts.append("")  # blank line between compressed block and first entry

    for e in entries:
        parts.append(e.heading)
        if e.body:
            parts.append(e.body)
        parts.append("")  # blank line between entries

    out = "\n".join(parts)
    # Collapse any triple-blank-line runs introduced by stitching.
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out


def archive_path_for(symbol: str, before_date: str, base_dir: Path) -> Path:
    """Canonical archive copy location: <base_dir>/archive/<SYM>_pre_<date>.md.

    Callers should write the *pre-compression* contents here before invoking
    `compress()`. The path is also embedded in the compressed-summary block
    so future readers can recover the full history.
    """
    return base_dir / "archive" / f"{symbol}_pre_{before_date}.md"
