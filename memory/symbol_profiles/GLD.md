# Symbol Profile — GLD

> Descriptive observations only. No trade recommendations. Per v1 contract, this file records what has been seen, never what should be done.

## Coverage
GLD is covered by **two strategies simultaneously** (per `config/strategy_rules.yaml`):

1. **`dual_momentum_taa`** (60% of portfolio capital) — GLD competes against SPY and TLT for the active sleeve allocation when momentum scoring selects it.
2. **`gold_permanent_overlay`** (10% of portfolio capital) — GLD as a permanent allocation regardless of momentum.

Note: the 2026-05-12 daily journal (line 21) flags that the Strategy A and Strategy C GLD allocations must be reconciled at decision time so they don't double-count. This is an open implementation item, not a settled rule.

## First-day observations (2026-05-12)
- ENTRY signal fired from `dual_momentum_taa` with trailing 12m return **+38.56%** (`journals/daily/2026-05-12.md` line 9).
- ENTRY signal also active from `gold_permanent_overlay` as the permanent 10% sleeve (same line).
- GLD was listed as a top candidate in `reports/pre_market/2026-05-12.md` (per journal line 11).
- No decision file was written; no position opened (journal line 12, line 17).

## Structural role (from backtest evidence)
Per `reports/learning/pivot_validation_2026-05-10.md`:

- GLD is held in this portfolio for its **diversifying / crisis-hedge** properties, not for expected return alone.
- **Realistic forward-return estimate: +5 to +8% CAGR.** This is materially lower than the +38.56% trailing 12m return observed today. The backtest team explicitly flagged this gap.
- GLD has had multi-year drawdowns: roughly **-20% to -30% during 2013-2015** and again during **2022's rate-hike cycle**. Gold is not a strict negative-correlation hedge; it can fall alongside stocks when real yields rise sharply.

## Correlation considerations
- TLT and SPY both fell in 2022 (per pivot_validation doc), which is the same window where GLD also drew down. The "uncorrelated three-strategy" thesis must be read in that light: correlations are regime-dependent, not constant.
- The gold_permanent_overlay is intended to provide left-tail protection in crises that hit equities, but the 2022 episode showed it does not always do so.

## Open questions for future review (do not act on yet)
- Did the GLD signal that fired today persist into actual entries? (Awaiting decision files.)
- Once positions exist, does the realized return on GLD over the holding period track closer to the trailing +38.56% or to the backtest's +5-8% estimate?
- How is the Strategy A vs Strategy C double-count issue resolved in practice?

## Caveats
- 1 day of operational data. Anything stronger than "we observed X" would be premature.
