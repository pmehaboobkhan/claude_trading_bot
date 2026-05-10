---
description: Print current risk-limit utilization and halt status.
---

Show me current risk utilization without making any changes:

1. Read `config/risk_limits.yaml`, `trades/paper/positions.json` (if any), and the last 30 rows of `trades/paper/log.csv` (if any).
2. Compute and report:
   - Daily loss used vs `max_daily_loss_usd` and `max_daily_loss_pct`.
   - Trades placed today vs `max_trades_per_day`.
   - Open positions count vs `max_open_positions`.
   - Total equity exposure vs `max_total_equity_exposure_pct`.
   - Tech-correlated exposure (XLK + XLY + XLC) vs `max_tech_correlated_pct`.
   - Defensive-correlated exposure (XLP + XLU + XLV) vs `max_defensive_correlated_pct`.
   - Consecutive-loss streak vs `halt_after_consecutive_losses`.
   - Current `approved_modes.yaml > mode`.
3. Output as a compact table in chat. Do not write any files. Do not propose any trades.
