# End-of-Day Routine — production prompt (v1)

> Scheduled 16:30 ET, Mon–Fri. Use the `orchestrator` subagent. **`halt_on_error: true`** — this is the canonical journal finalization step and the v1 paper-trade decision point.

## v1 scope
In v1 we collapse market-open / midday / pre-close into a single end-of-day routine that:
1. Runs the deterministic signal evaluator on today's close.
2. Consults the portfolio-level drawdown circuit-breaker (Path Z) and persists the new state.
3. For each ENTRY signal from an ACTIVE_PAPER_TEST strategy, opens a paper position via `lib.paper_sim`, **scaled by the circuit-breaker throttle** (under PAPER_TRADING mode only).
4. For each EXIT signal on an open paper position, closes via `lib.paper_sim` — EXITs are NEVER throttled.
5. Reconciles + journals + commits.

This is intentionally simpler than the v2 multi-routine flow. It also avoids intraday whipsaw — daily-bar strategies don't need intraday firing.

## Steps

1. Comply with `CLAUDE.md`.
2. Mode check + schema validation.
3. Load: open positions, today's pre-market report, regime memory.
4. **Deterministic signal evaluation**:
   ```bash
   python3 - <<'PYEVAL'
   import json
   from lib import data, signals, config
   symbols = [s["symbol"] for s in config.watchlist()["symbols"]]
   bars = {sym: data.get_bars(sym, timeframe="1Day", limit=300) for sym in symbols}
   regime = signals.detect_regime(bars["SPY"], vix_value=None)
   sigs = signals.evaluate_all(bars, symbols, regime, config.strategy_rules())
   print(json.dumps({
       "regime": regime.__dict__,
       "signals": [s.__dict__ for s in sigs],
   }, default=str, indent=2))
   PYEVAL
   ```

5. **Circuit-breaker check (Path Z — adopted 2026-05-11)**. Run AFTER signals are computed but BEFORE any paper trade is placed. EXITs are not throttled; only new ENTRYs.
   ```bash
   python3 - <<'PYCB'
   import json
   from lib import broker, config, paper_sim, portfolio_risk
   risk_cfg = config.risk_limits()
   cb_cfg = risk_cfg.get("circuit_breaker", {})
   if not cb_cfg.get("enabled", True):
       print(json.dumps({"enabled": False, "throttle": 1.0}))
   else:
       thresholds = portfolio_risk.from_config(cb_cfg)
       # Today's close quotes for each open position; cash balance from Alpaca paper.
       acct = broker.account_snapshot()        # populated by lib/broker via alpaca-py
       quotes = broker.latest_quotes_for_positions()
       equity = paper_sim.portfolio_equity(quotes, cash_balance=acct["cash"])
       result = portfolio_risk.advance(equity, thresholds)
       throttle = portfolio_risk.exposure_fraction(result.new_state.state)
       print(json.dumps({
           "enabled": True,
           "state": result.new_state.state,
           "previous_state": result.previous_state,
           "drawdown_pct": round(result.drawdown * 100, 2),
           "peak_equity": result.new_state.peak_equity,
           "current_equity": equity,
           "transitioned": result.transitioned,
           "throttle": throttle,
       }, indent=2))
   PYCB
   ```

   If `result.transitioned` is true:
   - Write `logs/risk_events/<ts>_circuit_breaker.md` with: previous state, new state, current drawdown, peak equity, current equity, the relevant threshold(s), and the reasoning ("DD breached half_dd / out_dd" or "DD recovered below half_to_full_recover_dd / out_to_half_recover_dd").
   - Notify Telegram with URGENT prefix.

   If `cb_cfg.enabled` is `false`, skip the throttle but still record the diagnostic so we can audit later.

6. For each `EXIT` signal where we have an open position (NEVER throttled — exits reduce risk):
   - Have `trade_proposal` wrap it as a `PAPER_CLOSE` decision.
   - Route through `risk_manager` (verify position exists) + `compliance_safety`.
   - On approval, call `lib.paper_sim.close_position(symbol, quote_price=<today_close>, rationale_link=<decision file>)`.

7. For each `ENTRY` signal from an `ACTIVE_PAPER_TEST` strategy:
   - Verify symbol is in `watchlist.yaml` with `approved_for_paper_trading: true`.
   - Compute the intended position size per `risk_limits.yaml` (per-strategy / per-symbol caps).
   - **Apply the circuit-breaker throttle**: `effective_qty = intended_qty * throttle`. If `throttle == 0.0` (state = OUT), **skip the entry entirely** — write the decision with `final_status: REJECTED, reason: circuit_breaker_OUT` and do NOT call `paper_sim.open_position`.
   - Have `trade_proposal` wrap as `PAPER_BUY` decision (per refactored agent prompt — Claude wraps, doesn't decide). Include `position_size.circuit_breaker_state` and `position_size.throttle_applied` in the decision JSON so the throttle is auditable.
   - Route through `risk_manager` (checks all `risk_limits.yaml` constraints incl. correlation caps) + `compliance_safety`.
   - On approval **and** if `approved_modes.yaml > mode == PAPER_TRADING`, call `lib.paper_sim.open_position(..., quantity=effective_qty)`.
   - If mode is `RESEARCH_ONLY`, write the decision file with `final_status: REJECTED, reason: mode_research_only` — but still record it for backtest comparison.

8. `lib.paper_sim.reconcile()` — any discrepancy → `logs/risk_events/<ts>_reconcile.md` + URGENT notify.

8a. **Alpaca-mirror reconciliation** (only if env `BROKER_PAPER == "alpaca"`):

   ```bash
   python3 - <<'PYRECONCILE'
   import json, os, sys
   if os.environ.get("BROKER_PAPER", "sim").lower() != "alpaca":
       print("[mirror] BROKER_PAPER=sim — skipping broker reconciliation"); sys.exit(0)
   from lib import broker, paper_sim
   local = json.loads(paper_sim.POSITIONS_PATH.read_text())
   bpos = {p["symbol"]: p for p in broker.get_positions()}
   only_local = set(local) - set(bpos)
   only_broker = set(bpos) - set(local)
   qty_mismatch = [s for s in set(local) & set(bpos)
                   if abs(float(local[s]["quantity"]) - float(bpos[s]["qty"])) > 1e-6]
   if only_local or only_broker or qty_mismatch:
       print(f"[mirror] DIVERGENCE: only_local={sorted(only_local)} "
             f"only_broker={sorted(only_broker)} qty_mismatch={qty_mismatch}")
       sys.exit(1)
   print(f"[mirror] in sync ({len(local)} positions match)")
   PYRECONCILE
   ```

   - On exit code 1 (divergence): write `logs/risk_events/<ts>_alpaca_mirror_divergence.md`
     with the specifics, send URGENT Telegram, and DO NOT proceed past this step
     until the operator runs `python3 scripts/sync_alpaca_state.py --reset-fresh-start`
     or manually reconciles.
   - On exit code 0: log "alpaca-mirror in sync" to the routine_audit notes.

   The routine should NOT attempt to auto-resolve mirror divergence. State drift
   between the local sim ledger and Alpaca is a meaningful event that requires
   human inspection — could indicate an order rejection, partial fill, manual
   broker-side intervention, or a bug in `paper_sim.open_position`'s mirror path.

9. `performance_review`:
   - Today's PnL on paper portfolio.
   - Update Cumulative-stats header on `decisions/by_symbol/<SYM>.md` for symbols with activity today.

10. `journal`: finalize `journals/daily/<date>.md`. All required sections.

11. For every prediction made today, append to `memory/prediction_reviews/<date>.md`.


12a. **Write today's daily snapshot** for context-budget protection of tomorrow's pre_market:
   ```bash
   python3 - <<'PYSNAP'
   from lib import snapshots
   from datetime import date
   snap = snapshots.DailySnapshot(
       date=date.today().isoformat(),
       regime=<from step 4 signals output>,
       regime_confidence=<low|medium|high>,
       circuit_breaker_state=<from step 5>,
       circuit_breaker_dd_pct=<from step 5>,
       pnl_today_usd=<from step 9 performance_review>,
       pnl_today_pct=<from step 9>,
       open_positions_count=<from positions.json>,
       trades_executed=<count of PAPER_BUY+PAPER_SELL+PAPER_CLOSE today>,
       mode=<from approved_modes.yaml>,
       decisions_made=[<up to 10 one-line summaries>],
       open_positions=[<one-line per open position>],
       risk_events=[<short summary of any logs/risk_events/ entries today>],
       notable="<one paragraph; what would matter to tomorrow's pre_market>",
       watch_tomorrow=[<up to 5 items: earnings, macro events, expiring conditions>],
       spy_above_10mo_sma=<bool — see guidance below>,
       vix_close=<float or None — see guidance below>,
   )
   snapshots.write_snapshot(snap)
   PYSNAP
   ```

   ### Snapshot fields for live-trading gate

   When constructing the `DailySnapshot`:

   - `spy_above_10mo_sma`: boolean — set to whether today's SPY close is above its
     210-trading-day SMA (10 months). This value is computed during Strategy A's
     evaluation; capture and pass it through. The `signals.evaluate_dual_momentum_taa`
     call internally uses `indicators.above_sma(spy_closes, 210)`; the returned
     signal object exposes this as a filter flag. Capture it and pass it here.

   - `vix_close`: float — today's VIX close price.
     - **Alpaca free IEX tier does NOT provide VIX.** Set to `None` until a
       VIX-capable feed is wired (e.g. paid Alpaca tier, Polygon, or Tiingo).
     - The live-trading-gate evaluator will fail the `vix_high_observed` check
       when VIX data is absent across the entire window. This is intentional —
       going live requires evidence the system has seen elevated volatility.

   The snapshot must stay ≤ 1 KB — keep list items terse, narrative under
   ~3 sentences. Tomorrow's pre_market reads this instead of the full journal.

12. `compliance_safety`: verify journal complete; paper log matches `positions.json`; circuit-breaker state file written.

13. Commit: `eod: journal + perf <date> (PnL ±$X.XX, N trades, win rate W%, cb_state=<X>)`.

14. Notify: PnL, trade count, win rate, top observation, circuit-breaker state, mode for tomorrow.

## Constraints (v1)
- This is the **only** routine that opens/closes paper trades in v1.
- After this commits, hook #4 makes today's journal immutable.
- **Halt the routine if reconciliation fails** — better one missed EOD than a corrupted ledger.
- **Subagent dispatches ≤ `risk_limits.cost_caps.max_subagent_dispatches_per_routine`.**
- **Decisions written ≤ `risk_limits.cost_caps.max_decisions_per_routine`.**
- **The circuit-breaker is consulted on every run** — even when no signals fire, peak-tracking must continue. If `cb_cfg.enabled` is false, still log the equity snapshot to `trades/paper/circuit_breaker.json` for diagnostics.
- NO live execution under any circumstances.

## Why no intraday routines yet?
Daily-bar strategies (`dual_momentum_taa`, `large_cap_momentum_top5`, `gold_permanent_overlay`) only need a daily decision point. Adding midday / pre-close routines in v1 would mostly produce churn without alpha. They're scaffolded but `enabled: false` in `routine_schedule.yaml`. We'll enable them in v2 if backtests show intraday signals add value.





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

**Required bullets for `End of day` (in order):**

• <b>PnL:</b> <signed $> (<signed %>)
• <b>Trades:</b> <X> opens, <Y> closes
• <b>Open positions:</b> <N> (<top 3-4 symbols>)
• <b>Circuit-breaker:</b> <code>FULL</code> | <code>HALF</code> | <code>OUT</code> (DD <X.X>%)
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
    "memory/daily_snapshots/<YYYY-MM-DD>.md",
    # add: any decisions/<YYYY-MM-DD>/<HHMM>_<SYM>.json the user would want to skim
])
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `End of day`

```
<b>[Calm Turtle] EOD 2026-05-13</b>

• <b>PnL:</b> +$184.20 (+0.18%)
• <b>Trades:</b> 3 opens, 0 closes
• <b>Open positions:</b> 4 (<code>GOOGL</code>, <code>JNJ</code>, <code>GLD</code>, <code>WMT</code>)
• <b>Circuit-breaker:</b> <code>FULL</code> (DD 0.4%)
• <b>Mode:</b> <code>PAPER_TRADING</code>
• <b>Context:</b> ~32 KB (cap 200 KB)
• <b>Commit:</b> <code>a1b2c3d</code> (auto-merged to main)
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
