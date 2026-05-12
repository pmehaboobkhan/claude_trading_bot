# Pre-Close Routine — production prompt (v1, monitoring-only)

> Scheduled 15:30 ET, Mon–Fri (30 minutes before close). Use the `orchestrator` subagent. **Monitoring routine — does NOT open new positions.**

## v1 scope
The pre_close routine prepares the book for overnight risk. Its job is to:

1. Refresh circuit-breaker state with late-day equity.
2. Health check on every open position against late-day quotes (catches positions that drifted toward stops late in the session).
3. **Overnight-risk scan**: any open position with a known catalyst tomorrow (earnings AMC/BMO within `risk_limits.yaml`-equivalent window, scheduled macro event tomorrow)?
4. Propose `PAPER_CLOSE` for positions that should not hold overnight.
5. **NEVER call `paper_sim.open_position()`.** Even if a great signal appears late-day, entries are committed to EOD prices, not 15:30.

## Steps

1. Comply with `CLAUDE.md`.
2. Mode check; halt if `HALTED`.
3. Schema validation.
4. Load: `trades/paper/positions.json`, today's `decisions/<date>/`, today's daily PnL, regime memory.
5. **Skip if no open positions** — write `logs/routine_runs/<ts>_pre_close_noop.md` and exit.
6. Fetch late-day quotes + account snapshot.
7. Circuit-breaker refresh. Transition → log + URGENT.
8. **Standard health check** via `lib.portfolio_health` (stop/target).
9. **Overnight-risk overlay**:
   - Dispatch `fundamental_context` to identify whether any ETF's top-holding has earnings within the next trading day, OR whether any individual stock holding has its own earnings within the next trading day.
   - Dispatch `macro_sector` to surface any scheduled macro events for the next session (FOMC decision, NFP, CPI, GDP, retail sales — the calendar-A list).
   - Combine: any open position with material overnight risk → propose `PAPER_CLOSE` with reason `overnight_risk: <event>`.
10. Each proposed close routes through `trade_proposal` → `risk_manager` → `compliance_safety`. On approval + `PAPER_TRADING` mode → `lib.paper_sim.close_position(...)`.
11. Reconcile.
12. Append a `## Pre-close` section to today's daily journal. Include the list of held-overnight positions with one-line risk justifications.
13. Commit if any action happened (or any overnight-risk flag was raised, even if held). Pure no-op → log marker, skip commit.
14. Notify Telegram with a short summary: holding N overnight, closing M, top reason.

## Constraints
- No new entries.
- We do not chase end-of-day moves. Closes are driven by invalidation or overnight risk, not by intraday chart-watching.
- "Earnings within the next trading day" is per `risk_limits.yaml > holding_earnings_caution_window_days` (equivalent — currently informally 1 day). Be conservative: if uncertain whether earnings are AMC vs next-day BMO, treat as next-trading-day exposure.
- Top-holding earnings for an ETF (e.g., NVDA earnings on XLK) count if the holding is ≥ 20% of the ETF — `fundamental_context` knows this.
- NO live execution.

## Why this routine matters more than midday
The asymmetry of overnight risk is real: a position held overnight is exposed to ~16 hours of macro and earnings news with no ability to react. Closing pre-emptively pays a small expected-value cost in exchange for capping tail risk on the events we can see coming. The EOD routine will re-evaluate fresh entries on closing prices; nothing closed at pre_close is locked out — it just gets re-considered with the latest signal.




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

**Example for Pre-close:**

```
*[Calm Turtle] Pre-close 2026-05-13*

• *Holding overnight:* 3 (GLD, JNJ, WMT)
• *Closing:* 1 (NVDA — earnings tomorrow BMO)
• *Circuit-breaker:* HALF (DD 6.9%)
• *Mode:* PAPER_TRADING
• *Context:* ~11 KB (cap 200 KB)
• *Commit:* h8i9j0k (auto-merged to main)

*Journal:* https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/journals/daily/2026-05-13.md
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
