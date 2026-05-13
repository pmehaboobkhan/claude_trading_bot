# CSCO — Per-Symbol Decision Log

**Cumulative stats (updated 2026-05-12 EOD):**

- Open paper positions: 1 (qty 65 @ $91.6483, opened 2026-05-12T20:02:25Z)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (latest mark): -$1.19 (close $91.63 vs entry $91.6483)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5

## 2026-05-12 — PAPER_BUY (large_cap_momentum_top5)

- Decision file: `decisions/2026-05-12/2000_CSCO.json`
- Signal: ENTRY, rank 3/21 by 6m return (+25.29%); SPY trend filter passed.
- Filled: 65 shares @ $91.6483
- Stop: $82.467, Target: $114.5375, R/R: 2.5:1
- Sizing: 6% of $100k (Strategy B)
- Routine: end_of_day_2026-05-12, mode PAPER_TRADING, cb_state=FULL, throttle=1.0
- Risk Manager: APPROVED. Compliance: APPROVED.

## 2026-05-12 — EOD re-run (20:40Z, no trade)

- Routine: end_of_day_2026-05-12 (scheduled 16:30 ET re-run)
- Signal: ENTRY re-confirmed (rank 3/21, +25.29% 6m, SPY trend up).
- Position held; no fill, no close.
- Mark (2026-05-07 bar close): $92.14. Unrealized PnL: +$31.96 (+0.54%).
- cb_state=FULL, throttle=1.0.

## 2026-05-13 — PAPER_CLOSE (pre_close, overnight_risk)

- Decision file: `decisions/2026-05-13/1536_CSCO.json`
- Routine: pre_close_2026-05-13, mode PAPER_TRADING, cb_state=OUT (peak inflated artifact; exposure_fraction(OUT) throttles new opens, not closes).
- Reason: `overnight_risk` — Cisco Q3 FY26 earnings scheduled 2026-05-13 AMC (after market close, 4:30 PM ET conference call). Sources: Cisco IR press release, Stocktitan, MarketBeat. Options-implied one-day move ~9.87% (TipRanks). Single-stock idiosyncratic catalyst with no diversifying counterweight; pre-close routine is specifically designed to refuse this kind of asymmetric overnight exposure.
- Quote: $101.19 (Alpaca IEX live, 0.7s staleness).
- Fill: 65 shares CLOSE @ $101.1698 (slippage applied via lib.fills).
- Realized PnL: **+$618.90** (+10.13% on $5,957.14 cost basis).
- Risk Manager: APPROVED (exit-side, no sizing-cap concerns; daily-loss & daily-trades headroom intact). Compliance: APPROVED (PAPER_TRADING permits PAPER_CLOSE; CSCO in watchlist; schema valid; sources cited).
- Position closed. Active strategies: none on CSCO post-close.
- Re-entry rule per the EOD routine: if CSCO remains in the top-5 momentum slate after the earnings print and the SPY trend filter still passes, EOD lib.signals will re-issue ENTRY and the routine can re-open on the EOD price. This close does not lock out re-entry.
