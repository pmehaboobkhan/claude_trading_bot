# Proposed update — `prompts/routines/{end_of_day,pre_close,market_open,midday}.md`

**Author:** Claude (assistant)
**Date:** 2026-05-15
**Status:** DRAFT — awaiting human PR review
**Reason:** Live `lib/paper_monitor.py` surfaced `approximate_input_kb=178` on 2026-05-14 end_of_day, with 4 of the 5 heaviest files being **non-required** inputs the LLM read on its own initiative. Recent pre_close runs hit 143 KB; market_open hit 115 KB. The 200 KB advisory cap will breach within ~1-2 days at current trajectory. Root cause: the routine prompts don't explicitly tell the orchestrator which files **not** to read. The orchestrator instinctively reads any file mentioned in any nearby context (e.g. "review today's pre-market report").

## What this changes

A single guidance block added near the top of each routine prompt that explicitly enumerates the files the orchestrator should NOT re-read. These are files whose content is either redundant (already summarized elsewhere), not needed for this routine's job, or grew faster than expected:

- **Raw market data dumps** (`data/market/<date>/*.json`) — written by pre_market for traceability, not needed downstream. EOD has its own market data fetch (Step 4).
- **Prior-day journal files** (`journals/daily/<yesterday>.md`) — what's needed about yesterday is already in `memory/daily_snapshots/<yesterday>.md` (the whole reason the snapshot pattern was introduced 2026-05-12).
- **The full pre_market report** when only the headline is needed (e.g. EOD doesn't need the full 18 KB report; a one-line summary in the snapshot suffices).

## Concrete inserts

> Insert the following block as a new "Context budget" subsection immediately after the existing "v1 scope" section in each of the 4 named routine prompts.

```markdown
## Context budget (added 2026-05-15)

The 200 KB advisory cap in `risk_limits.yaml > cost_caps` is real: routines that
breach it risk hitting model token limits mid-run or producing truncated output.
The 2026-05-12 daily-snapshot infrastructure exists exactly so you don't have to
read full journals from prior days. Stay under 150 KB by **not reading**:

- **Raw market data dumps** at `data/market/<date>/*.json`. These are written
  by pre_market for traceability; downstream routines should call
  `lib.data.get_bars()` for the specific symbols they need, not slurp the
  whole dump.
- **Prior-day journals** at `journals/daily/<yesterday>.md`. Read
  `memory/daily_snapshots/<yesterday>.md` instead — it's the same information
  bounded to ≤ 1 KB.
- **The full pre-market report** at `reports/pre_market/<date>.md` if today's
  pre-market wrote a `memory/daily_snapshots/<date>.md` capturing the headline.
  Read the snapshot first; only open the full report if the snapshot lacks
  what you need.

You may read these files **if and only if** the snapshot is missing or stale.
The `paper_trading_monitor.py > check_context_budget_trend` check will surface
the heaviest 5 files in the next routine run; if one of the above appears and
the snapshot was usable, that's a regression in the routine's reading habits.
```

## Why each file goes in the don't-read list

| File | Why redundant |
|---|---|
| `data/market/<date>/0630.json` (17 KB) | Pre_market's raw fetch output. Routines need *specific* quotes, not the dump. |
| `journals/daily/<yesterday>.md` (50 KB+) | Snapshot at `memory/daily_snapshots/<yesterday>.md` captures the same context in <1 KB by design. |
| `reports/pre_market/<date>.md` (18 KB) | The 1-line headline lives in the snapshot. The full report is for human review, not routine input. |

## Verification once merged

Run the monitor after the next EOD that follows the new prompt:
```bash
python3 scripts/paper_trading_monitor.py
```

Expected: `context_budget_trend` finding drops back into OK range (under 150 KB) within 1-2 routine runs. The heaviest_files list — if any WARN/FAIL persists — should no longer include the 3 files above (only legitimate inputs).

## Cumulative-pattern follow-ups (not blocking this PR)

If the 200 KB cap is still being approached after this lands, the next levers
are:

- **Per-symbol decision logs** (already covered by `lib/symbol_history.compress`
  — Performance Review's weekly job, not a routine concern).
- **Audit logs themselves** (already auto-archived after 30d via
  `scripts/archive_routine_logs.py`, EOD Step 0).
- **The daily journal itself** — at 45 KB the journal is the single biggest
  file. The journal is the routine's *output*, not input, so the routine
  can't avoid reading it as part of finalization. The lever here is the
  journal's own length budget: a per-routine-section soft cap of ~3 KB
  would keep the day's total under 25 KB. That's a behaviour change to the
  journal agent, separate from this draft.

## Why this is a PR, not a direct commit

`prompts/routines/*.md` is locked by hook #5 per `CLAUDE.md`. Production
routine prompts only change via human-reviewed PR.
