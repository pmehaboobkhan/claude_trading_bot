# JNJ — Per-Symbol Decision Log

**Cumulative stats (updated 2026-05-12 EOD):**

- Open paper positions: 0
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL: $0.00
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5 (signal valid, deferred today)

## 2026-05-12 — NO_TRADE (large_cap_momentum_top5)

- Decision file: `decisions/2026-05-12/2000_JNJ.json`
- Signal: ENTRY, rank 5/21 by 6m return (+20.17%); SPY trend filter passed.
- Outcome: NO_TRADE — deferred by max_trades_per_day=5 cap (first 5 opens consumed today's budget for GLD, GOOGL, XOM, CSCO, WMT). Will reconsider next routine if signal still confirms.
- Routine: end_of_day_2026-05-12, mode PAPER_TRADING, cb_state=FULL, throttle=1.0
- Risk Manager: REJECTED (limit binding). Compliance: APPROVED (NO_TRADE always permissible).
