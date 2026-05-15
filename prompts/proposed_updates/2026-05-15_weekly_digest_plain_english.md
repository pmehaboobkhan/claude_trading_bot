# Proposed update — `prompts/routines/weekly_review.md` (+ `CLAUDE.md` approved write paths)

**Author:** Claude (assistant)
**Date:** 2026-05-15
**Status:** DRAFT — awaiting human PR review
**Reason:** Operator wants a weekly "what happened" digest written in plain English (no jargon, no Sharpe/drawdown/profit-factor) delivered to their phone alongside the existing technical artifacts. Email delivery was discussed and deferred — the existing Telegram document-attachment path is sufficient and adds zero new infrastructure. The technical weekly journal + learning review continue unchanged; the digest is an *additional* artifact for human readability.

## What this changes

1. A new **step 5b** in `weekly_review.md` that produces `reports/weekly_digest/<YYYY-WW>.md` — a 400-700 word plain-English narrative of the week.
2. The Telegram document attachment list (step B) is updated to **include the digest as the first attachment** so it's the most prominent card in chat.
3. A new bullet in the required Telegram text-message bullets pointing the operator at the digest.
4. The SAFE_MODE section notes the digest is *reporting* (not learning) and therefore continues to run in SAFE_MODE.
5. `CLAUDE.md` approved-write-paths list is extended to include `reports/weekly_digest/`.

Email delivery is intentionally **not** in scope. If the operator later wants a real inbox copy, a follow-up proposal can add an `lib.notify_email` module and credentials; the digest artifact will be ready to ship through either channel.

## Concrete inserts

### 1) Insert new step 5b after the existing step 5 in `prompts/routines/weekly_review.md`

> Place this block immediately after the `Draft risk-rule review doc only if calibration drift is real → cap: ≤ 1.` line and before the existing step 6.

```markdown
5b. **Plain-English weekly digest** → `reports/weekly_digest/<YYYY-WW>.md`.

   Audience: the operator, no finance background assumed. This is the "what
   happened this week" summary that gets attached to Telegram. Reporting only —
   no learning writes, runs in SAFE_MODE.

   Style rules:
   - No jargon. Avoid "Sharpe", "drawdown", "alpha", "profit factor", "R/R",
     "beta", "ATR", "calibration". If a concept needs a finance term, define
     it inline in one short clause.
   - Dollars first, percent second. E.g. "we made $124 this week, about 0.4%
     of the account."
   - Short paragraphs, no tables, no bullet walls. Read like a friendly note.
   - Every factual claim grounded in a file we already wrote this week — never
     invent narrative.

   Required sections (in this order):

   1. **The bottom line** — 1-2 sentences. Did we make or lose money this
      week? How much in dollars and as a percent of the account? Is the
      account higher or lower than where it started the month?
   2. **What we did this week** — one short paragraph per trade we opened or
      closed. For each: what we bought or sold, on what day, and the
      plain-English reason ("the trend turned up", "the rule said to take
      profit", "the stop-loss triggered"). Pull facts from
      `trades/paper/log.csv` and the matching `decisions/<date>/*.json`.
   3. **Why we made those calls** — 2-3 sentences tying the week's decisions
      back to the strategy rules in plain terms. "We're a trend-following
      account, so when SPY's six-month return turned positive we leaned in."
      No rule names, no parameter values.
   4. **What surprised us** — anything that didn't go as expected: a trade
      that hit the stop, a signal that fired we didn't anticipate, a day the
      circuit-breaker throttled us. If nothing surprised us, say so honestly.
   5. **What we're watching next week** — 2-3 bullets in plain English. What
      would make us add to a position, what would make us cut one, what
      external event (earnings, Fed, etc.) is on the calendar.

   Length target: 400-700 words. If the week was quiet (zero trades), keep it
   under 250 words and say so directly.
```

### 2) Update the "Required bullets for `Weekly review`" list to add a digest pointer

> In the `### Step A — text message via lib.notify.send_html` section, insert this bullet immediately after the existing `Artifacts attached below:` bullet (so it's the last bullet — it acts as a "start here" pointer for the operator).

```
• <b>Plain-English digest:</b> first attachment below
```

### 3) Update the document-attachment example in step B

> Replace the existing `delivered = notify.send_documents_html([...])` block with this list (digest first, then the technical journal):

```python
delivered = notify.send_documents_html([
    "reports/weekly_digest/<YYYY-WW>.md",     # plain-English narrative, read first
    "journals/weekly/<YYYY-WW>.md",           # technical weekly journal
])
```

### 4) Update the worked example block to reflect the new bullet

> Replace the example with:

```
<b>[Calm Turtle] Weekly review WK-19 2026</b>

• <b>Period return:</b> +1.84%
• <b>Sharpe:</b> 1.21 (5d)
• <b>Win rate:</b> 67% (8W / 4L)
• <b>Max DD this week:</b> 2.1%
• <b>Recommendation:</b> <code>STAY_PAPER</code>
• <b>Context:</b> ~28 KB (cap 200 KB)
• <b>Commit:</b> <code>p4q5r6s</code> (auto-merged to main)
• <b>Artifacts attached below:</b> 2 files
• <b>Plain-English digest:</b> first attachment below
```

### 5) SAFE_MODE section — add one line clarifying the digest is reporting

> In the `## SAFE_MODE handling` section, append this line at the end of the "Specific steps to guard in this routine" list:

```markdown
Step 5b (plain-English digest) is **reporting**, not learning. It continues to
run in SAFE_MODE — operator visibility matters most when the LLM stack is
already under suspicion.
```

### 6) `CLAUDE.md` — add `reports/weekly_digest/` to approved write paths

> In the `## Approved write paths` section, change this line:

```markdown
- `reports/pre_market/`, `reports/end_of_day/`, `reports/learning/`
```

> To:

```markdown
- `reports/pre_market/`, `reports/end_of_day/`, `reports/learning/`, `reports/weekly_digest/`
```

## Why this design

- **Narrative artifact + technical artifact, both delivered.** The technical weekly journal stays unchanged so performance review, audit, and self-learning agents continue to consume the same structured data. The digest is purely a human-readability layer.
- **Telegram attachment, not email.** `lib/notify.py:253` already exposes `send_documents_html()` and the operator already receives weekly Telegram notifications. Email would require new credentials, a new module, and a PR to add a secret to config — out of scope for v1.
- **Digest goes first in the attachment list.** Telegram renders the first attachment most prominently. The operator should see the friendly narrative before the technical journal.
- **Runs in SAFE_MODE.** Reporting visibility is *more* important, not less, when the LLM stack is under suspicion. The digest writes to `reports/weekly_digest/`, not `memory/` or `prompts/proposed_updates/`, so it doesn't fall under the SAFE_MODE learning-suppression rule.

## Things deliberately not in this proposal

- **A digest template file under `templates/`.** The section structure is in the prompt itself; a separate template would just duplicate it and drift.
- **Email delivery.** Requires new infrastructure and credentials. Operator agreed to defer.
- **Backfilling digests for prior weeks.** Out of scope. The next Saturday run produces the first one.
- **A daily mini-digest.** EOD reports already exist; a daily plain-English digest is a separate proposal if the weekly one proves useful.

## Verification once merged

1. Manually trigger the weekly routine (or wait for Saturday 09:00 ET).
2. Confirm `reports/weekly_digest/<YYYY-WW>.md` exists, is 400-700 words, and contains all five required sections.
3. Confirm the Telegram notification carries two document attachments with the digest first.
4. Spot-check the digest for jargon — search for `Sharpe`, `drawdown`, `alpha`, `profit factor`, `R/R`. Hits = the prompt rule isn't being followed.

## Rollback

Delete step 5b, revert the Telegram attachment list to its single-file form, and remove `reports/weekly_digest/` from `CLAUDE.md`. No data migration needed; existing digests can be left in place or deleted.
