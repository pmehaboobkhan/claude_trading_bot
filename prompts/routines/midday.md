# Midday Routine — production prompt (v1, monitoring-only)

> Scheduled 12:00 ET, Mon–Fri. Use the `orchestrator` subagent. **Monitoring routine — does NOT open new positions.**

## v1 scope
The midday routine is the **second pass** of intraday monitoring, between market_open and pre_close. Its job is to:

1. Refresh circuit-breaker state with midday equity.
2. Re-run health check on every open position against midday quotes.
3. News scan on names where we have open positions (a midday breaking story might invalidate a thesis).
4. Propose `PAPER_CLOSE` for any position with an invalidation trigger.
5. **NEVER call `paper_sim.open_position()`.**

## Context budget (added 2026-05-15)

The 200 KB advisory cap in `risk_limits.yaml > cost_caps` is real: routines
that breach it risk hitting model token limits mid-run or producing
truncated output. The 2026-05-12 daily-snapshot infrastructure exists
exactly so you don't have to read full journals from prior days. Stay
under 150 KB by **not reading**:

- **Raw market data dumps** at `data/market/<date>/*.json`. These are
  written by pre_market for traceability; downstream routines should call
  `lib.data.get_bars()` for the specific symbols they need, not slurp the
  whole dump.
- **Prior-day journals** at `journals/daily/<yesterday>.md`. Read
  `memory/daily_snapshots/<yesterday>.md` instead — it's the same
  information bounded to ≤ 1 KB by design.
- **The full pre-market report** at `reports/pre_market/<date>.md` if
  today's pre-market wrote a `memory/daily_snapshots/<date>.md` capturing
  the headline. Read the snapshot first; only open the full report if the
  snapshot lacks what you need.

You may read these files **if and only if** the snapshot is missing or
stale. The `paper_trading_monitor.py > check_context_budget_trend` check
surfaces the heaviest 5 files in the next routine run; if one of the
above appears and the snapshot was usable, that's a regression in the
routine's reading habits worth flagging in the routine_audit notes.

## Steps

1. Comply with `CLAUDE.md`.
2. Mode check; halt if `HALTED`.
3. Schema validation.
4. Load: `trades/paper/positions.json`, today's `decisions/<date>/`, `memory/market_regimes/current_regime.md`.
5. **Skip the rest if no open positions** — write `logs/routine_runs/<ts>_midday_noop.md` and exit.
6. Fetch midday quotes + account snapshot (same pattern as market_open step 5).
7. Circuit-breaker refresh (same pattern as market_open step 6). On transition → `logs/risk_events/<ts>_circuit_breaker.md` + URGENT notify.
8. **News scan**: dispatch `news_sentiment` against the set of symbols with open positions. Look for material breaking news (earnings preannouncement, regulatory action, M&A) that would invalidate the original thesis.
9. Health check via `lib.portfolio_health.assess_positions(quotes)`. For each position with invalidation:
   - If trigger is stop/target → propose `PAPER_CLOSE` (same flow as market_open step 7).
   - If trigger is news-driven → `trade_proposal` wraps with the news source URL cited; same gates apply.
10. Reconcile via `lib.paper_sim.reconcile()`.
11. Append a `## Midday` section to today's daily journal.
12. **Commit only if action happened.** Pure no-op → log marker, skip commit.
13. Notify Telegram only on action.

## Constraints
- No new entries.
- No portfolio rebalancing in midday — that's pre-close's job.
- Daily-loss limit utilization is rechecked here. If today's PnL ≤ `risk_limits.yaml > halts > halt_after_daily_limit_breach` threshold → write `logs/risk_events/<ts>_daily_loss.md`, propose closing all positions, notify URGENT.
- News claims must cite source URLs. No URL → no claim → no action.
- NO live execution.

## Cadence notes
This is the only routine that runs `news_sentiment` against open positions specifically. pre_market scans the full watchlist; midday narrows to where we have skin. The asymmetry is deliberate — by midday the cost of being wrong about an open position is higher than the cost of missing a watchlist candidate.






## Composing the Telegram notification

GitHub `/blob/main/<path>` URLs do not work reliably for our users:
- Private repos return 404 to anyone not authenticated to GitHub in the
  current browser (mobile is the common case).
- Public repos race the auto-merge action by ~30 seconds; a fast click
  hits 404 before the merge completes.

**Solution: send reports as Telegram document attachments.** No GitHub
dependency. The user reads the file inline in Telegram on any device.

### Step A — text message via `lib.notify.send_html`

Bulleted format with bold labels. `lib.notify.send_html()` uses
`parse_mode: "HTML"` so `<b>bold</b>`, `<code>code</code>`, and `•` render natively.

**Required bullets for `Midday` (in order):**

• <b>Action:</b> <none | N closes>
• <b>Circuit-breaker:</b> <state> (DD <X.X>%)
• <b>Open positions:</b> <N>
• <b>News:</b> <N material on open names>
• <b>Mode:</b> <mode>
• <b>Context:</b> ~<N> KB (cap 200 KB)              ← from audit step's approximate_input_kb
• <b>Commit:</b> <code><short SHA></code> (auto-merged to main)
• <b>Artifacts attached below:</b> <N> file(s)

Rules:
- Never mention the feature branch name.
- Notify only on action or risk event; pure no-op runs skip Telegram entirely.
- Each bullet under one line on a phone (~50–60 chars).
- Total text under 1500 chars.

### Step B — file attachments via `lib.notify.send_documents_html`

After the text message succeeds, attach the artifacts produced this run:

```bash
python3 - <<'PYNOTIFY'
from lib import notify
delivered = notify.send_documents_html([
    # Usually no attachments on midday — only attach if you proposed/executed closes.
    # Otherwise pass [] and skip step B entirely.
    "journals/daily/<YYYY-MM-DD>.md",  # only if action taken
])
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `Midday`

```
<b>[Calm Turtle] Midday 2026-05-13</b>

• <b>Action:</b> 1 <code>PAPER_CLOSE</code> (<code>NVDA</code> — material news, downgrade)
• <b>Circuit-breaker:</b> HALF (DD 7.2%)
• <b>Open positions:</b> 2
• <b>News:</b> 1 material on open names
• <b>Mode:</b> <code>PAPER_TRADING</code>
• <b>Context:</b> ~7 KB (cap 200 KB)
• <b>Commit:</b> <code>h8i9j0k</code> (auto-merged to main)
• <b>Artifacts attached below:</b> 1 file
```

The example shows the TEXT MESSAGE only. The attachments appear in the chat
immediately after as native Telegram document cards the user can tap to read.

## Routine audit log (mandatory final step)

Before exiting (clean OR halted OR error), write one audit file via
`lib.routine_audit`:

```bash
python3 - <<'PYAUDIT'
from lib import routine_audit
audit = routine_audit.RoutineAudit(
    routine="<routine_name_snake_case>",
    started_at="<ISO start ts>",
    ended_at="<ISO end ts>",
    duration_seconds=<float>,
    exit_reason=<"clean"|"halted"|"error"|"noop">,
    files_read=[
        routine_audit.file_record(p)
        for p in [<list of absolute paths you Read during this run>]
    ],
    subagent_dispatches={"<agent>": <count>, ...},
    artifacts_written=[<list of repo-relative paths you Wrote>],
    commits=[<short SHAs you created>],
    notes="<one-line context: anything noteworthy>",
)
routine_audit.write_audit(audit)
PYAUDIT
```

Why this exists: this is the only observable view of context-budget usage
across routine runs. `approximate_input_kb` is a proxy for input-token cost
and is trended over time. If it starts growing without bound, that's the
signal to compress per-symbol histories or rotate memory files. Until then,
we trust the system.

The hook-written `_start.md` / `_end.md` markers are separate and unchanged.

## SAFE_MODE handling (added 2026-05-14 — Plan #4)

Before any step that writes to `memory/` (except `memory/daily_snapshots/`),
to `prompts/proposed_updates/`, or that dispatches the `self_learning` agent:

```python
from lib import config, operating_mode
mode = config.current_mode()
if mode == "SAFE_MODE":
    # Skip this step entirely. The hook safe_mode_writes.sh would block
    # the file write anyway, but the routine should not attempt it —
    # it wastes tokens and pollutes the audit trail.
    pass
```

Specific steps to guard in this routine:
- Any write to `memory/symbol_profiles/`, `memory/agent_performance/`,
  `memory/prediction_reviews/`, `memory/strategy_lessons/`,
  `memory/market_regimes/` (except `current_regime.md` which is operational).
- Any dispatch of the `self_learning` subagent.
- Any write to `prompts/proposed_updates/`.

Snapshots to `memory/daily_snapshots/` are operational, not learning, and
remain allowed in SAFE_MODE.

When `mode == SAFE_MODE`, the Telegram notification should append:
```
• <b>Mode:</b> <code>SAFE_MODE</code> (learning suppressed)
```

The routine_audit appendix MUST record `mode: SAFE_MODE` and a count of
skipped learning steps so the audit trail clearly shows learning was
intentionally suppressed.
