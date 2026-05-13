# Migrate routine notifications from MarkdownV1 to HTML

## Context
Today's pre-market routine sent the user a duplicate Telegram message. Diagnosis at `logs/routine_runs/2026-05-13_103325_pre_market_audit.md` notes: the agent's first send used Telegram's MarkdownV1 with raw underscore tokens (`PAPER_TRADING`, `NO_SIGNAL`, `bullish_trend`); MarkdownV1 mis-rendered them as broken italics; the agent re-sent with backtick-escaping. Two messages with effectively identical content reached the user.

## Fix
`lib/notify.py` now provides additive HTML-mode functions:
- `notify.send_html(message)` — replaces `notify.send()`
- `notify.send_document_html(path, *, caption=...)` — replaces `notify.send_document(...)`
- `notify.send_documents_html(paths, *, caption=...)` — replaces `notify.send_documents(...)`
- Helpers: `notify.bold(text)`, `notify.code(text)`, `notify.link(text, url)`, `notify.escape_html(text)`

Telegram HTML mode escapes only `&`, `<`, `>` (vs MarkdownV1's quirky underscore handling). Tokens like `PAPER_TRADING` pass through unchanged.

## Required prompt changes (per routine)

In each of the 8 routine prompts:
- `prompts/routines/pre_market.md`
- `prompts/routines/market_open.md`
- `prompts/routines/midday.md`
- `prompts/routines/pre_close.md`
- `prompts/routines/end_of_day.md`
- `prompts/routines/weekly_review.md`
- `prompts/routines/monthly_review.md`
- `prompts/routines/self_learning_review.md`

Update the "Composing the Telegram notification" section.

### Before (current)

```
*[Calm Turtle] Pre-market 2026-05-13*

• *Regime:* range_bound (low conf)
• *Signals:* 7 ENTRY, 17 NO_SIGNAL
• *Top:* GOOGL (+35.3% 6m mom)
• *Mode:* PAPER_TRADING
• *Context:* ~18 KB (cap 200 KB)
• *Commit:* d10f9b6 (auto-merged to main)
• *Artifacts attached below:* 2 files
```

Sent via:
```python
notify.send(message)
```

### After (HTML)

```
<b>[Calm Turtle] Pre-market 2026-05-13</b>

• <b>Regime:</b> <code>range_bound</code> (low conf)
• <b>Signals:</b> 7 ENTRY, 17 <code>NO_SIGNAL</code>
• <b>Top:</b> <code>GOOGL</code> (+35.3% 6m mom)
• <b>Mode:</b> <code>PAPER_TRADING</code>
• <b>Context:</b> ~18 KB (cap 200 KB)
• <b>Commit:</b> <code>d10f9b6</code> (auto-merged to main)
• <b>Artifacts attached below:</b> 2 files
```

Sent via:
```python
notify.send_html(message)
```

Use `<code>...</code>` for: mode names (PAPER_TRADING, RESEARCH_ONLY, SAFE_MODE), regime classifications (bullish_trend, range_bound), signal action names (NO_SIGNAL, ENTRY), symbol tickers (SPY, GOOGL, IEF), commit SHAs, file paths.

Use `<b>...</b>` for: section labels (Regime:, Signals:, Top:), the header line.

Do NOT escape `*` or `_` — they're literals in HTML mode.

DO escape user-input or report-derived text that might contain `&`, `<`, `>`. The `notify.escape_html(text)` helper does this. For example, a thesis line that quotes the report:
```python
thesis = "GOOGL above 10mo SMA & ranked 1st"
bullet = f"• <b>Top:</b> <code>GOOGL</code> ({notify.escape_html(thesis)})"
```

### Step B (attachments) change

Replace:
```python
notify.send_documents([...])
```
with:
```python
notify.send_documents_html([...])
```

The attachment payloads themselves are not parsed — only an optional caption is. If you pass a caption, it must be HTML-formatted.

## Tests
After PR lands and a routine runs:
- Telegram message arrives once (no retry-with-escaping cycle).
- Mode names, regime classifications, symbol tickers all render in monospace.
- No "FAILED to clear Markdown parser" entries in subsequent audit logs.

## Migration order
Land routine-by-routine if preferred — both `notify.send()` and `notify.send_html()` coexist. After all 8 routines migrate, the legacy `send` / `send_document` / `send_documents` functions can be deprecated in a follow-up commit.
