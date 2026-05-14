# NVDA — Per-Symbol Decision Log

**Cumulative stats (created 2026-05-14 EOD):**

- Open paper positions: 0
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL: n/a (no position)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5 (signal valid 2026-05-14, blocked by CB OUT + data staleness)

## 2026-05-14 — NO_TRADE (large_cap_momentum_top5, end_of_day)

- Decision file: `decisions/2026-05-14/2038_NVDA.json`
- Routine: end_of_day_2026-05-14, mode PAPER_TRADING, cb_state=OUT, throttle=0.0.
- Signal: ENTRY (rank 5/21 by 6m return +18.90%, SPY trend filter passed). NVDA promoted from rank 7 (hold-zone) on 2026-05-13 to rank 5 (ENTRY) today on a +3.46pp 6m return move — only *net-new* ENTRY in the slate today (AMZN slipped from rank 5 → 6 in the opposite direction).
- Decision: **NO_TRADE** with reason `circuit_breaker_OUT AND data_staleness_breach`.
  - CB state OUT mechanically blocks new opens (peak $119,140.25 inflated artifact persists into the 7th routine; DD 15.37%).
  - Daily-bar feed staleness is 6 calendar days (latest 2026-05-08 vs today 2026-05-14); `max_data_staleness_seconds = 60` exceeded.
- Intended sizing pre-throttle: ~25 shares (~$5,881 ≈ 5.88% of $100k, Strategy B target 6%). NVDA's watchlist cap is 10% (tightest in basket vs 15% standard) per watchlist note. Actual: 0 shares.
- Quote at close $235.25 (Alpaca IEX, 20:00:02Z). Stop $211.73, Target $294.06, nominal R/R 2.5:1.
- Risk Manager: APPROVED on NO_TRADE (reduces no risk). Compliance: APPROVED.
- Watch tomorrow: if either gate clears (CB peak fix lands via `prompts/proposed_updates/cb_equity_source.md` OR feed catches up), reconsider on the EOD-2026-05-15 signal.
