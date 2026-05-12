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
A GitHub Action immediately fast-forward-merges that branch into `main`
and deletes the source branch (see `.github/workflows/auto_merge_claude.yml`).
By the time the user reads your Telegram message, the feature branch no
longer exists.

- Artifact links: use `https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/<path>`.
- Commits: cite the short SHA only. Do not suffix with the branch name.
- Status: "auto-merged to main" or omit branch info.
- Notify only if action was taken (a close, a risk event, a regime call) — pure no-ops are logged but not pushed to Telegram.
