# Midday Routine — production prompt (v1, monitoring-only)

> Scheduled 12:00 ET, Mon–Fri. Use the `orchestrator` subagent. **Monitoring routine — does NOT open new positions.**

## v1 scope
The midday routine is the **second pass** of intraday monitoring, between market_open and pre_close. Its job is to:

1. Refresh circuit-breaker state with midday equity.
2. Re-run health check on every open position against midday quotes.
3. News scan on names where we have open positions (a midday breaking story might invalidate a thesis).
4. Propose `PAPER_CLOSE` for any position with an invalidation trigger.
5. **NEVER call `paper_sim.open_position()`.**

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

This routine commits to a `claude/...` feature branch (Claude Code default).
A GitHub Action immediately fast-forward-merges that branch into `main` and
deletes the source branch (see `.github/workflows/auto_merge_claude.yml`).
By the time the user reads your Telegram message, the feature branch is gone.

**Required format: bulleted, with bold labels.** Telegram renders Markdown
(`*bold*`) and the `•` character is a literal bullet that all clients
handle correctly. **Do NOT send prose paragraphs** — bullets are easier
to skim on mobile.

**Required fields, in order**, on each notification:

1. Header — `*[Calm Turtle] <routine title> <YYYY-MM-DD>*` on its own line.
2. One bulleted line per metric (regime, signals, PnL, etc. — see per-routine list below).
3. `• *Context:* ~<N> KB (cap 200 KB)` — populate N from the `approximate_input_kb`
   you computed in the audit step (sum of `files_read[].bytes` divided by 1024).
   This is a proxy for input-token cost, exposed so the user can spot context drift.
4. `• *Commit:* <short SHA> (auto-merged to main)` — short SHA only; never
   suffix with `on claude/<branch>`.
5. Artifact links (one per line), each as
   `*<Label>:* https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/<path>`.
   Use `/blob/main/<path>` — these resolve once the auto-merge completes
   (~30 seconds after push) and remain stable forever.

**Rules:**
- Never mention the feature branch name. Ever.
- Notify only if action was taken or a risk event fired. Pure no-op runs
  are logged to `logs/routine_runs/` but skip Telegram.
- Keep each bullet under one line on a phone (~50–60 chars). Truncate
  long thesis text and link to the full report instead.
- Total message length under 1500 chars; Telegram caps at 4096.

**Example for Midday:**

```
*[Calm Turtle] Midday 2026-05-13*

• *Action:* none (positions healthy)
• *Circuit-breaker:* HALF (DD 7.2%)
• *Open positions:* 3
• *News:* 0 material on open names
• *Mode:* PAPER_TRADING
• *Context:* ~7 KB (cap 200 KB)

(no commit — no-op run, marker in logs/routine_runs/)
```

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
