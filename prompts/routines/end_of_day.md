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

9. `performance_review`:
   - Today's PnL on paper portfolio.
   - Update Cumulative-stats header on `decisions/by_symbol/<SYM>.md` for symbols with activity today.

10. `journal`: finalize `journals/daily/<date>.md`. All required sections.

11. For every prediction made today, append to `memory/prediction_reviews/<date>.md`.

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

The routine commits to a `claude/...` feature branch (Claude Code default).
A GitHub Action immediately fast-forward-merges that branch into `main`
and deletes the source branch (see `.github/workflows/auto_merge_claude.yml`).

This means: **by the time the user reads your Telegram message, the feature
branch no longer exists**. Never reference the feature branch by name in the
notification.

Compose links as follows:

- **Artifacts**: link to the file on the `main` branch using the form
  `https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/<path>`.
  These URLs resolve as soon as the auto-merge completes (~30 seconds after
  your push) and remain stable forever.
- **Commits**: cite the short SHA (e.g. `d10f9b6`). Do **not** suffix it
  with "on claude/<branch>" — commit SHAs are independent of branch refs
  and remain valid after the feature branch is deleted. If you want a
  clickable link, use `https://github.com/pmehaboobkhan/claude_trading_bot/commit/<sha>`.
- **Status**: it is fine to say "auto-merged to main" or to omit branch
  information entirely. Do not mention the feature branch name.

Example for pre_market:

```
[Calm Turtle] Pre-market 2026-05-12
Regime: range_bound (low confidence)
7 ENTRY signals; top candidate GLD (Strategy A + C agree)
Commit: d10f9b6 (auto-merged to main)
Report: https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/reports/pre_market/2026-05-12.md
Journal: https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/journals/daily/2026-05-12.md
```
