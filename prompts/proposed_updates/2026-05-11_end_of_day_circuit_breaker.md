# Proposed update — `prompts/routines/end_of_day.md`

**Author:** Claude (assistant)
**Date:** 2026-05-11
**Status:** DRAFT — awaiting human PR review
**Reason:** Wire the Path Z circuit-breaker (decided 2026-05-11) into the only routine that opens/closes paper trades in v1. The breaker module and config block already exist (`lib/portfolio_risk.py`, `config/risk_limits.yaml > circuit_breaker`); this change makes the routine actually consult it.

## What this changes
- After step 4 (deterministic signal eval) and BEFORE step 5/6 (close/open paper trades), the routine computes today's portfolio equity, consults the circuit-breaker, persists the new state, and scales any new ENTRY position sizes by `exposure_fraction(state)`.
- EXIT signals are NEVER throttled — closing a position is risk reduction.
- A FULL → HALF or HALF → OUT transition emits a `logs/risk_events/<ts>_circuit_breaker.md` entry and an URGENT Telegram notification.

## Proposed replacement for steps 4 → 6 in `prompts/routines/end_of_day.md`

> Replace the current steps 4, 5, and 6 with the block below. Other steps unchanged. Step numbers will shift by +1 after this insertion.

```markdown
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

5. **Circuit-breaker check (Path Z — decided 2026-05-11)**. Run AFTER signals are computed but BEFORE any paper trade is placed. EXITs are not throttled; only new ENTRYs.
   ```bash
   python3 - <<'PY'
   import json
   from lib import config, paper_sim, portfolio_risk
   risk_cfg = config.risk_limits()
   cb_cfg = risk_cfg.get("circuit_breaker", {})
   thresholds = portfolio_risk.from_config(cb_cfg)
   # Today's close quotes per open position; cash balance from broker/sim.
   quotes = {...}                              # populate from data.get_bars latest close
   cash_balance = ...                          # from Alpaca account or internal ledger
   equity = paper_sim.portfolio_equity(quotes, cash_balance)
   result = portfolio_risk.advance(equity, thresholds)
   print(json.dumps({
       "state": result.new_state.state,
       "previous_state": result.previous_state,
       "drawdown_pct": round(result.drawdown * 100, 2),
       "peak_equity": result.new_state.peak_equity,
       "current_equity": equity,
       "transitioned": result.transitioned,
       "throttle": portfolio_risk.exposure_fraction(result.new_state.state),
   }, indent=2))
   PY
   ```
   If `cb_cfg.enabled` is `false`, **skip** the throttle but still record state for diagnostics.

   If `result.transitioned` is true:
   - Write `logs/risk_events/<ts>_circuit_breaker.md` with: previous state, new state, current drawdown, peak equity, current equity, and the reasoning ("DD breached half_dd / out_dd" or "DD recovered below half_to_full_recover_dd / out_to_half_recover_dd").
   - Notify Telegram with URGENT prefix.

6. For each `EXIT` signal where we have an open position: (unchanged from current step 5 — exits are NEVER throttled)
   - `trade_proposal` wraps as `PAPER_CLOSE`. `risk_manager` + `compliance_safety` gates.
   - On approval, `lib.paper_sim.close_position(symbol, quote_price=<today_close>, rationale_link=<decision file>)`.

7. For each `ENTRY` signal from an `ACTIVE_PAPER_TEST` strategy:
   - Verify symbol is in `watchlist.yaml` with `approved_for_paper_trading: true`.
   - **Apply the circuit-breaker throttle**: compute the intended position size per strategy rules, then multiply by the `throttle` value from step 5. If `throttle == 0.0` (state = OUT), **skip the entry entirely** — write the decision with `final_status: REJECTED, reason: circuit_breaker_OUT` and do not call `paper_sim.open_position`.
   - `trade_proposal` wraps as `PAPER_BUY`. Include `position_size.circuit_breaker_state` and `position_size.throttle_applied` in the decision JSON so the throttle is auditable.
   - Route through `risk_manager` + `compliance_safety`. On approval and if `mode == PAPER_TRADING`, call `lib.paper_sim.open_position(..., quantity=intended_qty * throttle)`.
```

## Tests
The state machine itself is locked in by `tests/test_portfolio_risk.py` (34 tests). The integration above is exercised manually in the first paper-trading days; we'll add an end-to-end test once we have a routine harness.

## Rollback
If the breaker behaves badly in paper trading, set `circuit_breaker.enabled: false` in `config/risk_limits.yaml` via a one-line PR. The routine code path falls back to no throttling. All other paper-trading behaviour is unchanged.

## Why this is a PR, not a direct commit
`prompts/routines/*.md` is locked by hook #5 per `CLAUDE.md`. Production routine prompts only change via human-reviewed PR.
