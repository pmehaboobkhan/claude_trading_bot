# Symbol Profile — GOOGL

> Descriptive observations only. No trade recommendations.

## Coverage
GOOGL is covered by **`large_cap_momentum_top5`** (30% of portfolio capital). It is selected when it ranks in the top 5 of the large-cap universe by trailing 6-month return, subject to the SPY trend filter.

## First-day observations (2026-05-12)
- ENTRY signal fired with **rank 1** in the large-cap momentum sleeve.
- Trailing **6-month return: +35.31%** (`journals/daily/2026-05-12.md` line 9).
- GOOGL was listed as a top candidate in `reports/pre_market/2026-05-12.md` (per journal line 11).
- No decision file was written; no position opened (journal line 12, line 17).

## Survivor-bias caveat (important context)
Per `reports/learning/pivot_validation_2026-05-10.md`:

- The Strategy B large-cap universe was assembled from **today's** mega-cap names. By construction, this universe is conditioned on **forward knowledge of which companies became mega-caps** over the backtest window.
- The Strategy B backtest produced a headline **+1857% total return** over 2013-2026, but the pivot_validation document explicitly flags this as **inflated by survivor bias**.
- The realistic forward-return estimate for `large_cap_momentum_top5` is roughly **+10-14% CAGR**, well below the backtest headline.
- Practical implication for GOOGL specifically: its inclusion in the universe today does not mean it would have been chosen by a non-survivor-biased screen 5 or 10 years ago.

## Structural notes
- SPY trend filter (per `config/strategy_rules.yaml` description in journal context): the strategy only opens positions when SPY is above its 200d MA. As of 2026-05-12, SPY is +4.71% above its 50d and above its 200d (`journals/daily/2026-05-12.md` line 8), so the trend filter is passing today.
- News connector is offline (journal line 15). Any decision on GOOGL will carry `news_unavailable` as a risk factor.

## Macro context
- Regime call today: **range_bound, low confidence**. Momentum strategies historically underperform in chop; this is structural context, not a forecast.

## Open questions for future review
- Does GOOGL's actual realized 6m return after entry track closer to the +35.31% trailing or to a more modest mean-reverting outcome?
- How does the news-unavailable risk factor evolve once the connector is built?

## Caveats
- 1 day of operational data. Symbol-specific patterns require N >= 5 marked PRELIMINARY, and stronger claims require larger N.
