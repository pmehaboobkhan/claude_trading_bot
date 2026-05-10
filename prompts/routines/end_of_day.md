# End-of-Day Routine — production prompt (v1)

> Scheduled 16:30 ET, Mon–Fri. Use the `orchestrator` subagent. **`halt_on_error: true`** — this is the canonical journal finalization step and the v1 paper-trade decision point.

## v1 scope
In v1 we collapse market-open / midday / pre-close into a single end-of-day routine that:
1. Runs the deterministic signal evaluator on today's close.
2. For each ENTRY signal from an ACTIVE_PAPER_TEST strategy, opens a paper position via `lib.paper_sim` (under PAPER_TRADING mode only).
3. For each EXIT signal on an open paper position, closes via `lib.paper_sim`.
4. Reconciles + journals + commits.

This is intentionally simpler than the v2 multi-routine flow. It also avoids intraday whipsaw — daily-bar strategies don't need intraday firing.

## Steps

1. Comply with `CLAUDE.md`.
2. Mode check + schema validation.
3. Load: open positions, today's pre-market report, regime memory.
4. **Deterministic signal evaluation**:
   ```bash
   python3 - <<'PY'
   import json
   from lib import data, signals, config
   symbols = [s["symbol"] for s in config.watchlist()["symbols"]]
   bars = {sym: data.get_bars(sym, timeframe="1Day", limit=250) for sym in symbols}
   regime = signals.detect_regime(bars["SPY"], vix_value=None)
   sigs = signals.evaluate_all(bars, symbols, regime, config.strategy_rules())
   print(json.dumps({
       "regime": regime.__dict__,
       "signals": [s.__dict__ for s in sigs],
   }, default=str, indent=2))
   PY
   ```
5. For each `EXIT` signal where we have an open position:
   - Have `trade_proposal` wrap it as a `PAPER_CLOSE` decision.
   - Route through `risk_manager` (verify position exists) + `compliance_safety`.
   - On approval, call `lib.paper_sim.close_position(symbol, quote_price=<today_close>, rationale_link=<decision file>)`.

6. For each `ENTRY` signal from an `ACTIVE_PAPER_TEST` strategy:
   - Verify symbol is in `watchlist.yaml` with `approved_for_paper_trading: true`.
   - Have `trade_proposal` wrap as `PAPER_BUY` decision (per refactored agent prompt — Claude wraps, doesn't decide).
   - Route through `risk_manager` (checks all `risk_limits.yaml` constraints incl. correlation caps) + `compliance_safety`.
   - On approval **and** if `approved_modes.yaml > mode == PAPER_TRADING`, call `lib.paper_sim.open_position(...)`.
   - If mode is `RESEARCH_ONLY`, write the decision file with `final_status: REJECTED, reason: mode_research_only` — but still record it for backtest comparison.

7. `lib.paper_sim.reconcile()` — any discrepancy → `logs/risk_events/<ts>_reconcile.md` + URGENT notify.

8. `performance_review`:
   - Today's PnL on paper portfolio.
   - Update Cumulative-stats header on `decisions/by_symbol/<SYM>.md` for symbols with activity today.

9. `journal`: finalize `journals/daily/<date>.md`. All required sections.

10. For every prediction made today, append to `memory/prediction_reviews/<date>.md`.

11. `compliance_safety`: verify journal complete; paper log matches `positions.json`.

12. Commit: `eod: journal + perf <date> (PnL ±$X.XX, N trades, win rate W%)`.

13. Notify: PnL, trade count, win rate, top observation, mode for tomorrow.

## Constraints (v1)
- This is the **only** routine that opens/closes paper trades in v1.
- After this commits, hook #4 makes today's journal immutable.
- **Halt the routine if reconciliation fails** — better one missed EOD than a corrupted ledger.
- **Subagent dispatches ≤ `risk_limits.cost_caps.max_subagent_dispatches_per_routine`.**
- **Decisions written ≤ `risk_limits.cost_caps.max_decisions_per_routine`.**
- NO live execution under any circumstances.

## Why no intraday routines yet?
Daily-bar strategies (`sector_relative_strength_rotation`, `regime_defensive_tilt`, etc.) only need a daily decision point. Adding midday / pre-close routines in v1 would mostly produce churn without alpha. They're scaffolded but `enabled: false` in `routine_schedule.yaml`. We'll enable them in v2 if backtests show intraday signals add value.
