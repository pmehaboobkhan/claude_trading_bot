# WMT — Per-Symbol Decision Log

**Cumulative stats (updated 2026-05-12 EOD):**

- Open paper positions: 1 (qty 46 @ $130.1160, opened 2026-05-12T20:02:25Z)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (latest mark): -$1.20 (close $130.09 vs entry $130.116)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5

## 2026-05-12 — PAPER_BUY (large_cap_momentum_top5)

- Decision file: `decisions/2026-05-12/2000_WMT.json`
- Signal: ENTRY, rank 4/21 by 6m return (+24.30%); SPY trend filter passed.
- Filled: 46 shares @ $130.116
- Stop: $117.081, Target: $162.6125, R/R: 2.5:1
- Sizing: 6% of $100k (Strategy B)
- Routine: end_of_day_2026-05-12, mode PAPER_TRADING, cb_state=FULL, throttle=1.0
- Risk Manager: APPROVED. Compliance: APPROVED.

## 2026-05-12 — EOD re-run (20:40Z, no trade)

- Routine: end_of_day_2026-05-12 (scheduled 16:30 ET re-run)
- Signal: ENTRY re-confirmed (rank 4/21, +24.30% 6m, SPY trend up).
- Position held; no fill, no close.
- Mark (2026-05-07 bar close): $130.24. Unrealized PnL: +$5.70 (+0.10%).
- cb_state=FULL, throttle=1.0.
