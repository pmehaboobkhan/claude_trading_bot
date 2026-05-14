# XOM — Per-Symbol Decision Log

**Cumulative stats (updated 2026-05-12 EOD):**

- Open paper positions: 1 (qty 40 @ $148.6497, opened 2026-05-12T20:02:25Z)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (latest mark): -$1.19 (close $148.62 vs entry $148.6497)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5

## 2026-05-12 — PAPER_BUY (large_cap_momentum_top5)

- Decision file: `decisions/2026-05-12/2000_XOM.json`
- Signal: ENTRY, rank 2/21 by 6m return (+33.58%); SPY trend filter passed.
- Filled: 40 shares @ $148.6497
- Stop: $133.758, Target: $185.775, R/R: 2.5:1
- Sizing: 6% of $100k (Strategy B)
- Routine: end_of_day_2026-05-12, mode PAPER_TRADING, cb_state=FULL, throttle=1.0
- Risk Manager: APPROVED. Compliance: APPROVED.

## 2026-05-12 — EOD re-run (20:40Z, no trade)

- Routine: end_of_day_2026-05-12 (scheduled 16:30 ET re-run)
- Signal: ENTRY re-confirmed (rank 2/21, +33.58% 6m, SPY trend up).
- Position held; no fill, no close.
- Mark (2026-05-07 bar close): $146.51. Unrealized PnL: -$85.59 (-1.44%). **Lone unrealized loser today.**
- Stop ($133.758) is $12.75/share below mark; ample headroom. No exit triggered.
- cb_state=FULL, throttle=1.0.

## 2026-05-13 — EOD held (re-confirm ENTRY, no trade)

- Routine: end_of_day_2026-05-13, mode PAPER_TRADING, cb_state=OUT, throttle=0.0.
- Signal: ENTRY re-confirmed (rank 2/21 +29.76% 6m, SPY trend up).
- Quote at close $142.12 (Alpaca IEX live, 20:00:05Z; pre_close 19:36Z saw $151.33 — significant late-day reversal driven by oil-complex weakness).
- Mark vs entry $148.6497 → -$261.19 (-4.39%). Stop $133.758 (5.9% headroom).
- Decision: continue holding; no new decision file written.
- Watch: XOM gave back all of today's earlier gains in the final 25 minutes. Headroom to stop is now the tightest in the book.

## 2026-05-14 — EOD held (re-confirm ENTRY, no trade)

- Routine: end_of_day_2026-05-14, mode PAPER_TRADING, cb_state=OUT, throttle=0.0.
- Signal: ENTRY re-confirmed (rank 2/21 +27.73% 6m, SPY trend up).
- Quote at pre_close (19:41Z in-market): $152.55. Post-close IEX last $143.48 (degraded; bid $143.48 / ask $0.0 — discarded as a real mark).
- Mark vs entry $148.6497 → **+$156.01 (+2.62%)**. Stop $133.758 (12.3% headroom — recovered substantially vs yesterday's 5.9%).
- Decision: continue holding; no new decision file written.
- **Ex-dividend flag**: XOM goes ex-div 2026-05-15 ($1.03/share Q2 dividend declared 2026-05-02; record date 2026-05-15). Expect ~$1.03 (~0.68%) mechanical price drop at the open — NOT a thesis invalidation. Stop $133.758 sits ~$17.79 below the ex-div-adjusted mark; zero stop-risk impact.
- News tailwind this week: Iran/Strait of Hormuz oil-price spike; Q1 already beat ($85.14B rev, $1.16 EPS); Texas redomicile vote May 27 (governance, not thesis).

**Cumulative stats (updated 2026-05-14 EOD):**

- Open paper positions: 1 (qty 40 @ $148.6497)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (mark $152.55): +$156.01 (+2.62%)
- Win rate: n/a (no closed trades)
- Active strategies: large_cap_momentum_top5
