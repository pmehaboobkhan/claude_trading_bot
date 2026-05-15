# Proposed update — heartbeat-on-noop + news connector probe (routine prompts)

**Author:** Claude (assistant)
**Date:** 2026-05-15
**Status:** DRAFT — awaiting human PR review
**Reason:** Operator reported they had no confirmation that scheduled remote agents ran today, because the routines explicitly suppress Telegram on no-op runs ("Notify Telegram only if action was taken" — [market_open.md:99](../routines/market_open.md), [midday.md:56](../routines/midday.md)). Silence is indistinguishable from "the routine never fired." Additionally, the persistent `news_unavailable` label has become a default rather than a probe result — midday on 2026-05-14 successfully fetched news via WebSearch ([journals/daily/2026-05-14.md:68](../../journals/daily/2026-05-14.md)) while pre_market the same day did not, suggesting the connector is reachable but the routine isn't actually probing.

This proposal:
1. Adds a single short **heartbeat Telegram message** on every no-op run (positions = 0, no closes, no CB transition, no risk event) so the operator sees daily proof of life.
2. Switches the news-connector status from "default offline" to "probe-driven" by calling `scripts/news_probe.py` and reading its `data/news/<date>/_status.md` verdict.

Companion code (already on this branch): `lib/notify.send_heartbeat()` + `scripts/news_probe.py` + tests.

## What this changes

| File | Change |
|---|---|
| `prompts/routines/market_open.md` | Step 11 — add heartbeat-on-noop. New "Heartbeat composition" subsection. |
| `prompts/routines/midday.md` | Step 13 — add heartbeat-on-noop. Step 8 — call news probe before dispatching `news_sentiment`. |
| `prompts/routines/pre_market.md` | Step (whichever runs news_sentiment) — call news probe; only mark `news_unavailable` if probe says UNREACHABLE. |
| `prompts/routines/pre_close.md`, `prompts/routines/end_of_day.md` | Same heartbeat-on-noop pattern, for symmetry. |
| `CLAUDE.md` "Approved write paths" | (no change needed — `data/news/` is already approved). |

The action-summary path is **unchanged** — when a routine takes real action it still uses `send_html()` with the full message, not the heartbeat.

## Concrete inserts

### 1) `prompts/routines/market_open.md` — replace step 11

Currently:

```markdown
11. Notify Telegram only if action was taken.
```

Replace with:

```markdown
11. Notify Telegram on every run:
    - **Action runs** (close, circuit-breaker transition, risk event) → send the full action summary via `lib.notify.send_html()` (see "Composing the Telegram notification" below).
    - **No-op runs** → send a single-line heartbeat via `lib.notify.send_heartbeat()`. This costs ≤1 message per routine per day and gives the operator daily proof-of-life. See "Heartbeat composition" below.
```

### 2) `prompts/routines/market_open.md` — new subsection after "Composing the Telegram notification"

```markdown
## Heartbeat composition (no-op runs only)

Use `lib.notify.send_heartbeat()`. Required fields:

```python
from lib import notify
notify.send_heartbeat(
    routine="market_open",
    timestamp_utc="<orchestrator wall-clock ISO8601>",
    mode="<from approved_modes.yaml>",
    open_positions=<int>,
    cb_state="<FULL|HALF|OUT|n/a>",
    equity_usd=<float from broker.account_snapshot()>,
    exit_reason="noop",
)
```

The heartbeat message:
- Is short (≤ 6 lines).
- Includes routine name + UTC timestamp + mode + position count + circuit-breaker state + equity.
- Is the **only** Telegram message sent on a no-op run.
- Is NOT sent if the routine takes action (the action summary supersedes it).

Skip the heartbeat (and exit silent) only when `mode == HALTED` — the halt
audit log already covers that case.
```

### 3) `prompts/routines/midday.md` — replace step 13

Currently:

```markdown
13. Notify Telegram only on action.
```

Replace with:

```markdown
13. Notify Telegram on every run:
    - **Action runs** → `send_html()` with the full summary.
    - **No-op runs** → `send_heartbeat()` with routine="midday". One message per day.
```

### 4) `prompts/routines/midday.md` — replace step 8 (news scan)

Currently:

```markdown
8. **News scan**: dispatch `news_sentiment` against the set of symbols with open positions.
```

Replace with:

```markdown
8. **News scan**:
   a. Run `python3 scripts/news_probe.py --quiet` first. Read the verdict from `data/news/<date>/_status.md`.
   b. If verdict is `UNREACHABLE` → mark all open names `news_unavailable` per CLAUDE.md (treat as risk factor, never bullish silence). Skip the dispatch.
   c. If verdict is `REACHABLE` → dispatch `news_sentiment` against the set of symbols with open positions. Look for material breaking news (earnings preannouncement, regulatory action, M&A) that would invalidate the original thesis.
```

### 5) `prompts/routines/pre_market.md` — wrap the `news_sentiment` dispatch with the same probe

Find the `news_sentiment` bullet (currently around line 41) and prefix it with the probe step. Mirror the midday.md pattern. If the probe says UNREACHABLE, the routine continues to mark `news_unavailable` (no behavior change for the unhappy path); if the probe says REACHABLE, the routine dispatches news_sentiment instead of defaulting to "v1 offline."

### 6) `prompts/routines/pre_close.md` and `prompts/routines/end_of_day.md` — heartbeat for symmetry

These routines already always-notify on closes / EOD-summary, but if the routine somehow exits with no fills and no risk events (e.g. flat book + no rebalance), the same heartbeat pattern applies. Reviewer's call — low priority.

## Rationale for the heartbeat-vs-silence trade-off

The original "silent on no-op" rule was written to avoid Telegram spam. With 3 monitoring routines per trading day (market_open / midday / pre_close) and a typical 0-2 actions per day, the worst case is **3 extra messages per trading day** — well below the noise threshold. The information value (operator confidence that the system is alive) is high. Telegram already supports muting/scheduling on the client side if the operator wants to dampen them further.

## Verification before merging

- `pytest tests/test_notify.py tests/test_news_probe.py tests/test_paper_sim_reconcile.py -v` — all green.
- `python3 scripts/news_probe.py` — locally returns REACHABLE for SEC EDGAR.
- `scripts/bootstrap_env.sh` — runs idempotently.
- Spot-check one no-op routine after merge: expect exactly one heartbeat message in the Telegram chat for that run.

## Rollback plan

If heartbeats prove too chatty, revert the prompt changes only — `lib.notify.send_heartbeat()` and `scripts/news_probe.py` are additive and harmless even if unused.
