# Current market regime — 2026-05-12 (pre-market 06:30 ET)

- **Regime:** `range_bound`
- **Confidence band:** `low`
- **Source of truth:** Deterministic `lib.signals.detect_regime` against SPY daily bars (Alpaca IEX). See `reports/pre_market/2026-05-12.md` and `data/market/2026-05-12/0630.json` for the input snapshot.

## Indicators cited
1. **SPY above 50-day MA**: `true` — pct from 50DMA = **+4.71%** (`lib.signals` output, regime.indicators.spy_pct_from_50dma = 0.04714).
2. **SPY above 200-day MA**: `true` — long-term uptrend intact (`lib.signals` output, regime.indicators.spy_above_200dma).
3. **Proxy 20-day annualized vol**: **18.35%** (`lib.signals` output, regime.indicators.proxy_vol_20d_annualized_pct = 18.3465). VIX unavailable on the free IEX feed; the proxy is the effective vol used.

## Counter-evidence
- "Could break out either direction" — `lib.signals` flagged this verbatim. Range-bound with low confidence means a directional break could come without warning. Bias to NO_TRADE on edge-cases.

## What works in this regime
- Trend-followers that have already locked in a long position can hold (no exit signal triggered).
- Momentum-rank rotations within a steady SPY trend are still tradeable (large_cap_momentum_top5 fires today).
- Permanent diversifier (gold_permanent_overlay) continues.

## What fails in this regime
- Aggressive breakout-buying — false breakouts are common in range_bound + low_confidence regimes.
- Mean-reversion against the higher timeframe trend (still up vs 200DMA).
- Re-entering positions that just exited (whipsaw risk).

## Recommended caution level
**Medium.** The deterministic signals fire cleanly today, but low-confidence regime classifications widen the error band on momentum reads. Defer to Risk Manager + Compliance gates on any trade decision (no decisions in pre-market by design).

## Date stamp
- Computed at: 2026-05-12 (pre-market routine)
- Set by: orchestrator (adopted from `lib.signals.detect_regime`)
- Next refresh: end_of_day routine.
