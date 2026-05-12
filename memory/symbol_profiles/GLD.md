# Symbol Profile — GLD

Descriptive observations only. No buy/sell recommendations.

## Identity
- Ticker: GLD (SPDR Gold Trust)
- Asset class: physical-gold-backed ETF
- Approved in `config/watchlist.yaml` for paper trading (per project state context)

## Role in strategy mix
- **Strategy A — `dual_momentum_taa` (60% capital):** GLD is one of three macro assets (SPY / IEF / GLD) eligible for the trend-following sleeve.
- **Strategy C — `gold_permanent_overlay` (10% capital):** GLD is the permanent allocation target, intended as diversifier and crisis hedge regardless of momentum signal.

## Today's signal (2026-05-12)
- Signal 1: ENTRY, `dual_momentum_taa`, 12m return +38.56%. Source: `journals/daily/2026-05-12.md` line 9.
- Signal 2: ENTRY, `gold_permanent_overlay`, permanent 10%. Source: same.

## Known characteristics (from prior backtest / pivot reports)
- GLD is one of the assets whose presence helps Strategy A diversify against simultaneous SPY/bond drawdowns (e.g. 2022-type rising-rates regime).
- Gold is treated explicitly as a crisis-hedge component in Strategy C; the permanent allocation does not depend on momentum confirmation.

## Known risks / flags
- **Double-count risk:** GLD appears in both Strategy A and Strategy C signal sets on 2026-05-12. The EOD note in the journal explicitly flags the need to reconcile Strategy A's macro allocation vs Strategy C's permanent 10% so total GLD exposure does not exceed the intended cap (journal line 21).
- Data staleness: latest bar 2026-04-23 (journal line 16). 6m/12m momentum inputs tolerate this lag; intraday or fill-quality work would not.

## Observation log
- 2026-05-12: surfaced as ENTRY signal from two strategies simultaneously; no position opened (pre-market is research-only).

## Open questions for future review
1. When the first GLD trade closes, was the realized 5d / 20d return consistent with the long-bias prediction?
2. Did the double-count guard in the position-sizing logic correctly cap GLD exposure across A + C?

## Sources
- `journals/daily/2026-05-12.md`
- `reports/learning/backtest_findings_2026-05-10.md`
- `reports/learning/pivot_validation_2026-05-10.md`
