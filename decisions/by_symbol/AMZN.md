# AMZN — Per-Symbol Decision Log

**Cumulative stats (updated 2026-05-13 EOD):**

- Open paper positions: 0
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL: n/a (no position)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5 (signal valid, blocked today by CB OUT + data staleness)

## 2026-05-13 — NO_TRADE (large_cap_momentum_top5, end_of_day)

- Decision file: `decisions/2026-05-13/2050_AMZN.json`
- Routine: end_of_day_2026-05-13, mode PAPER_TRADING, cb_state=OUT, throttle=0.0.
- Signal: ENTRY (rank 5/21 by 6m return +21.11%, SPY trend filter passed). AMZN displaced JNJ in the top-5 vs yesterday's pre-market.
- Decision: **NO_TRADE** with reason `circuit_breaker_OUT AND data_staleness_breach`.
  - CB state OUT mechanically blocks new opens (peak $119,140.25 inflated artifact persists; DD 16.16%).
  - Daily-bar feed staleness is 19 calendar days (latest 2026-04-24 vs today 2026-05-13); `max_data_staleness_seconds = 60` is exceeded by orders of magnitude. Per `CLAUDE.md`: stale data = NO_TRADE for that symbol.
- Intended sizing pre-throttle: ~21 shares (~$5,948 ≈ 5.95% of $100k, Strategy B target 6%). Actual: 0 shares.
- Quote at close $283.24 (Alpaca IEX live, 20:00:00Z). Stop $254.92, Target $354.05, nominal R/R 2.5:1.
- Risk Manager: APPROVED on NO_TRADE (reduces no risk). Compliance: APPROVED.
- Watch tomorrow: if either gate clears (CB peak fix lands via `prompts/proposed_updates/cb_equity_source.md` OR feed catches up), reconsider on the EOD-2026-05-14 signal.
