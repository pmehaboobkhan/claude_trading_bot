# Current Market Regime — 2026-05-12

**Proposed regime:** `range_bound`
**Confidence band:** `low`
**Date stamped:** 2026-05-12 (pre-market routine)

## Indicators (all sourced from `lib.signals.detect_regime` on 2026-05-12, see `data/market/2026-05-12/0630.json`)

1. **SPY above 50DMA:** `true` (+4.71% above 50DMA).
2. **SPY above 200DMA:** `true`.
3. **Proxy 20d annualized volatility:** 18.35% (VIX feed not available on Alpaca IEX free tier; `vix_value=None` so signals.detect_regime substituted realized-vol proxy).
4. SPY last close 708.41 (300-bar history loaded).

## Why `range_bound` rather than `bullish_trend`
`lib.signals.detect_regime` classified the tape `range_bound` with `low` confidence. SPY is positive vs both 50DMA and 200DMA (which would normally read bullish), but the proxy vol is meaningfully elevated (18.35% annualized) and the model's counter-evidence flag ("Could break out either direction") fires. We adopt the deterministic call verbatim, per pre_market.md step 6 ("macro_sector: adopt the regime classification from step 5 (do not re-derive)").

## Counter-evidence (what would change the call)
- SPY closes below 50DMA -> reclassify toward `bearish_trend` or wait for confirmation.
- Proxy vol spikes above ~25% annualized -> `high_vol`.
- SPY closes above recent swing high with vol falling -> upgrade to `bullish_trend`.
- A VIX feed wire-up at >20 with rising slope -> reclassify `high_vol`.

## Signals known to work in `range_bound`
- Mean-reversion entries on extreme oversold/overbought (NOT used by v1 strategies).
- Patient trend-following with trailing stops (Strategy A's 10-month MA filter is well-suited).
- Equal-weight diversification across uncorrelated risk assets (Strategy A+B+C is exactly this).

## Signals known to fail in `range_bound`
- Breakout-chasing without confirmation.
- Aggressive sector rotation (the rejected v0 strategies failed here).
- Single-strategy concentration.

## Recommended caution level
**Medium.** Trend filters are still on (SPY > 10-month MA per Strategy B output), but vol is elevated and regime confidence is low. Position sizing should respect `max_position_size_pct` strictly; no over-allocation against the macro ETF cap.

## Operator notes
- This is the **first** persisted regime record; prior memory was empty (clean repo state).
- News connector unavailable -> macro narrative is limited to price-based evidence only.
