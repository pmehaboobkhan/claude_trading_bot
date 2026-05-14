# GOOGL — Per-Symbol Decision Log

**Cumulative stats (updated 2026-05-12 EOD):**

- Open paper positions: 1 (qty 15 @ $397.9096, opened 2026-05-12T20:02:25Z)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (latest mark): -$1.19 (close $397.83 vs entry $397.9096)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5

## 2026-05-12 — PAPER_BUY (large_cap_momentum_top5)

- Decision file: `decisions/2026-05-12/2000_GOOGL.json`
- Signal: ENTRY, rank 1/21 by 6m return (+35.31%); SPY trend filter passed.
- Filled: 15 shares @ $397.9096
- Stop: $358.047, Target: $497.2875, R/R: 2.5:1
- Sizing: 6% of $100k (Strategy B 30% allocation / 5 names)
- Routine: end_of_day_2026-05-12, mode PAPER_TRADING, cb_state=FULL, throttle=1.0
- Risk Manager: APPROVED. Compliance: APPROVED.

## 2026-05-12 — EOD re-run (20:40Z, no trade)

- Routine: end_of_day_2026-05-12 (scheduled 16:30 ET re-run)
- Signal: ENTRY re-confirmed (rank 1/21, +35.31% 6m, SPY trend up).
- Position held; no fill, no close.
- Mark (2026-05-07 bar close): $397.89. Unrealized PnL: -$0.29 (-0.01%).
- cb_state=FULL, throttle=1.0.

## 2026-05-13 — EOD held (re-confirm ENTRY, no trade)

- Routine: end_of_day_2026-05-13, mode PAPER_TRADING, cb_state=OUT, throttle=0.0.
- Signal: ENTRY re-confirmed (rank 1/21 +36.81% 6m, SPY trend up).
- Quote at close $382.23 (Alpaca IEX live, 20:00:02Z; pre_close 19:36Z saw $402.96 — late-day give-back).
- Mark vs entry $397.9096 → -$235.19 (-3.94%). Stop $358.047 (6.3% headroom).
- Decision: continue holding; no new decision file written. Position is now this session's largest single-name unrealized loss.
- Watch tomorrow: monitor for further give-back. Stop is 6% below close so still ample headroom but tighter than yesterday.

## 2026-05-14 — EOD held (re-confirm ENTRY, no trade)

- Routine: end_of_day_2026-05-14, mode PAPER_TRADING, cb_state=OUT, throttle=0.0.
- Signal: ENTRY re-confirmed (rank 1/21 +38.42% 6m, SPY trend up).
- Quote at pre_close (19:41Z in-market): $401.68. Post-close IEX last $377.65 (degraded; bid $377.65 / ask $0.0 — discarded as a real mark).
- Mark vs entry $397.9096 → **+$56.56 (+0.95%)**. Stop $358.047 (10.9% headroom — recovered vs yesterday's 6.3%).
- Decision: continue holding; no new decision file written.
- News flow this week: Anthropic ~$200B/5yr commitment to Google Cloud (2026-05-11); Googlebook product launch with Acer/ASUS/Dell/HP/Lenovo. Tone neutral-to-bullish. Next earnings 2026-07-22 (outside near-term window).

**Cumulative stats (updated 2026-05-14 EOD):**

- Open paper positions: 1 (qty 15 @ $397.9096)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (mark $401.68): +$56.56 (+0.95%)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5
