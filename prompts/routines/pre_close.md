# Pre-Close Routine — production prompt (v1, monitoring-only)

> Scheduled 15:30 ET, Mon–Fri (30 minutes before close). Use the `orchestrator` subagent. **Monitoring routine — does NOT open new positions.**

## v1 scope
The pre_close routine prepares the book for overnight risk. Its job is to:

1. Refresh circuit-breaker state with late-day equity.
2. Health check on every open position against late-day quotes (catches positions that drifted toward stops late in the session).
3. **Overnight-risk scan**: any open position with a known catalyst tomorrow (earnings AMC/BMO within `risk_limits.yaml`-equivalent window, scheduled macro event tomorrow)?
4. Propose `PAPER_CLOSE` for positions that should not hold overnight.
5. **NEVER call `paper_sim.open_position()`.** Even if a great signal appears late-day, entries are committed to EOD prices, not 15:30.

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

**Required bullets for `Pre-close` (in order):**

• <b>Holding overnight:</b> <N> (<top symbols>)
• <b>Closing:</b> <M> (<reason one-liner>)
• <b>Circuit-breaker:</b> <state> (DD <X.X>%)
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
    "journals/daily/<YYYY-MM-DD>.md"
])
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `Pre-close`

```
<b>[Calm Turtle] Pre-close 2026-05-13</b>

• <b>Holding overnight:</b> 3 (<code>GLD</code>, <code>JNJ</code>, <code>WMT</code>)
• <b>Closing:</b> 1 (<code>NVDA</code> — earnings tomorrow BMO)
• <b>Circuit-breaker:</b> HALF (DD 6.9%)
• <b>Mode:</b> <code>PAPER_TRADING</code>
• <b>Context:</b> ~11 KB (cap 200 KB)
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
