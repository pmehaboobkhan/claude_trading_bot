# Market Open Routine — production prompt (v1, monitoring-only)

> Scheduled 09:35 ET, Mon–Fri (5 minutes after open). Use the `orchestrator` subagent. **Monitoring routine — does NOT open new positions.**

## v1 scope
The market_open routine is a **monitoring layer**, not an entry-generating layer. Entries happen only at EOD against closing prices — that is where our backtest evidence lives. The job here is to:

1. Refresh circuit-breaker state with opening equity (in case overnight news moved the portfolio meaningfully).
2. Detect overnight gaps that breached an open position's stop or take-profit.
3. Propose `PAPER_CLOSE` for any position with an invalidation trigger.
4. **NEVER call `paper_sim.open_position()`.** ENTRY signals from `lib.signals` are ignored in this routine.

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

1. Comply with `CLAUDE.md`. When uncertain, NO_TRADE.
2. Mode check: read `config/approved_modes.yaml`. If `HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit.
3. Schema validation: run `python3 tests/run_schema_validation.py`.
4. Load: `trades/paper/positions.json`, `trades/paper/circuit_breaker.json` (if exists), today's `reports/pre_market/<date>.md`, last 5 daily journals.
5. **Fetch opening quotes** for every open position only (not the whole watchlist):
   ```bash
   python3 - <<'PYQUOTES'
   import json
   from lib import broker
   acct = broker.account_snapshot()
   quotes = broker.latest_quotes_for_positions()
   print(json.dumps({
       "cash": acct["cash"],
       "equity": acct["equity"],
       "buying_power": acct["buying_power"],
       "quotes": quotes,
   }, indent=2))
   PYQUOTES
   ```
   If no open positions exist, skip to step 9.
6. **Circuit-breaker refresh**:
   ```bash
   python3 - <<'PYCB'
   import json
   from lib import config, paper_sim, portfolio_risk
   risk_cfg = config.risk_limits()
   cb_cfg = risk_cfg.get("circuit_breaker", {})
   thresholds = portfolio_risk.from_config(cb_cfg)
   # equity from step 5
   equity = ...   # paper_sim.portfolio_equity(quotes, cash_balance=acct["cash"])
   result = portfolio_risk.advance(equity, thresholds)
   print(json.dumps({
       "state": result.new_state.state,
       "previous_state": result.previous_state,
       "drawdown_pct": round(result.drawdown * 100, 2),
       "transitioned": result.transitioned,
   }, indent=2))
   PYCB
   ```
   If `result.transitioned` is true → write `logs/risk_events/<ts>_circuit_breaker.md`, notify URGENT Telegram.
7. **Health check on every open position** via `lib.portfolio_health`:
   ```bash
   python3 - <<'PYHEALTH'
   import json
   from lib import portfolio_health
   healths = portfolio_health.assess_positions(quotes)   # quotes from step 5
   to_close = [portfolio_health.health_as_dict(h) for h in healths if h.should_close()]
   print(json.dumps(to_close, indent=2))
   PYHEALTH
   ```
   For any position with `invalidation_triggers` non-empty:
   - `trade_proposal` wraps as a `PAPER_CLOSE` decision file at `decisions/<date>/<HHMM>_<SYM>.json`. Include `invalidation_triggers` verbatim in the decision JSON.
   - `risk_manager` verifies the position exists and the close is appropriate.
   - `compliance_safety` final gate.
   - On approval (and `mode == PAPER_TRADING`), call `lib.paper_sim.close_position(symbol, quote_price=<current>, rationale_link=<decision_file>)`.
8. `lib.paper_sim.reconcile()` — discrepancy → `logs/risk_events/<ts>_reconcile.md` + URGENT notify.
9. Append a `## Market open` section to today's `journals/daily/<date>.md` summarising: opening equity, CB state, any closes proposed/executed, any gap flags.
10. **Commit only if anything actionable happened** (close, circuit-breaker transition, risk event). If routine was pure no-op, write `logs/routine_runs/<ts>_market_open_noop.md` and skip the commit.
11. Notify Telegram only if action was taken.

## Constraints (hard rules)
- **No new entries.** Ignore ENTRY signals from `lib.signals`. If you find yourself drafting a PAPER_BUY decision in market_open, stop — that's a bug.
- **EXITs are never throttled by the circuit-breaker** — closing reduces risk and always proceeds if invalidation is real.
- Subagent dispatches ≤ `risk_limits.cost_caps.max_subagent_dispatches_per_routine`.
- NO live execution.

## Why monitoring-only
Our three v1 strategies (`dual_momentum_taa`, `large_cap_momentum_top5`, `gold_permanent_overlay`) all operate on daily bars and use slow signals (12-month momentum, 10-month SMA). They emit ENTRY/EXIT only on closing prices — that's what the backtest validated. Adding intraday entries would compound risk we have no evidence for. The monitoring job is real: catching overnight gaps that breached a stop, and refreshing the circuit-breaker before midday.






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

**Required bullets for `Market open` (in order):**

• <b>Action:</b> <N <code>PAPER_CLOSE</code> on overnight gap | none>
• <b>Circuit-breaker:</b> <prev → new state | unchanged> (DD <X.X>%)
• <b>Open positions:</b> <N>
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
    "journals/daily/<YYYY-MM-DD>.md",
    # if any: "logs/risk_events/<latest>_circuit_breaker.md"
])
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `Market open`

```
<b>[Calm Turtle] Market open 2026-05-13</b>

• <b>Action:</b> 1 <code>PAPER_CLOSE</code> (<code>GOOGL</code> — overnight gap below stop)
• <b>Circuit-breaker:</b> FULL → HALF (DD 8.4%)
• <b>Open positions:</b> 3
• <b>Mode:</b> <code>PAPER_TRADING</code>
• <b>Context:</b> ~9 KB (cap 200 KB)
• <b>Commit:</b> <code>e5f6g7h</code> (auto-merged to main)
• <b>Artifacts attached below:</b> 2 files
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
