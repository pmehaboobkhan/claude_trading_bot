# Current market regime

> Observation file. Updated each pre-market routine. Older entries archived to `history/`.

- **As of:** 2026-05-12 (pre-market)
- **Regime:** `bullish_trend`
- **Confidence:** `medium`
- **Source:** `lib.signals.detect_regime(spy_bars, vix_value=None)`
- **Bars input:** `backtests/_yfinance_cache/SPY.csv`, last bar `2026-05-08T00:00:00Z`
- **Indicators (verbatim from `lib.signals.detect_regime`):**
  - `spy_above_50dma`: `true`
  - `spy_above_200dma`: `true`
  - `spy_pct_from_50dma`: `+7.88%`
  - `vix`: `null` (no live feed)
  - `proxy_vol_20d_annualized_pct`: `10.45%`
  - `effective_vix_used`: `10.45` (proxy substituted for VIX)
- **Counter-evidence:** "Trend can break on macro shocks."

## Narrative context

SPY is above both its 50-day and 200-day MAs and 7.88% above the 50-day. 20-day realized volatility is benign at ~10.5% annualized, below the 18 effective-VIX threshold that gates `bullish_trend`. Confidence is medium rather than high because (a) the VIX proxy is realized rather than implied volatility, and (b) the input bars end Friday 2026-05-08, so the read is one trading day old.

Strategy-level read consistent with regime:
- Strategy A picks GLD as dual-momentum winner (+39.59% 12m vs SHV +3.98%); SPY clears filters at +32.95% 12m but is outranked.
- Strategy B trend filter active (SPY above 210d MA); top-5 momentum names are mixed across Communication Services (GOOGL), Tech (CSCO), Consumer Staples (WMT), Energy (XOM), and Health Care (JNJ).
- Strategy C: permanent GLD overlay reinforces Strategy A.

The combined allocation profile is GLD-heavy (~70% on paper); the Risk Manager must reconcile this against `max_macro_etf_position_pct = 60.0%` before any paper fill.
