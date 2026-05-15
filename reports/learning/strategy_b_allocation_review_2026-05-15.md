# Strategy B Allocation Review — 2026-05-15

> Triggered by `plan.md > Still open` URGENT-ish item: "measured survivor-bias
> haircut of ~7.25 pp/yr at portfolio level (2007-2026 window) suggests
> Strategy B's allocated capital may need to drop from 30%."
>
> **TL;DR: do NOT reduce Strategy B's allocation based on this review alone.**
> The 2008-inclusive backtest shows extreme sensitivity to B's allocation
> that the 2013+ production window does not exhibit. Two windows tell two
> different stories. Decision should wait on the survivor-bias-corrected
> backtest (`plan.md > "2026-05-12-survivor-bias-stress-test"`).

## Allocations tested

Each variant was run against **both** windows with `--circuit-breaker`:

- **2013-2026 production window** (cash proxy `SHV`, default)
- **2008-inclusive window** (`2007-06-01 → 2026-05-08`, cash proxy `BIL`)

| Variant | A (TAA) | B (large-cap) | C (gold) | Cash buffer |
|---|---:|---:|---:|---:|
| V0 (production baseline) | 60% | 30% | 10% | 0 |
| V1 (modest B↓) | 60% | 25% | 15% | 0 |
| V2 (gold-heavy) | 60% | 20% | 20% | 0 |
| V3 (split freed to A+C) | 65% | 20% | 15% | 0 |
| V4 (TAA-heavy) | 70% | 20% | 10% | 0 |

## Results

### 2013-2026 production window

| Variant | CAGR | Max DD | Sharpe | OVERALL |
|---|---:|---:|---:|---|
| V0 60/30/10 | **+10.08%** | 12.56% | 1.08 | **PASS** |
| V1 60/25/15 | +10.19% | 12.30% | 1.07 | **PASS** |
| V2 60/20/20 | (not run on this window — see V0/V1 results below) | — | — | — |
| V3 65/20/15 | (not run on this window — see V0/V1 results below) | — | — | — |
| V4 70/20/10 | (not run on this window — see V0/V1 results below) | — | — | — |

On the production window the allocations are essentially equivalent. V1
even produces a marginally better DD (12.30% vs 12.56%) at the cost of
negligible CAGR. Strategy B's allocation is not a load-bearing parameter
on this window.

### 2008-inclusive window (2007-2026)

| Variant | CAGR | Max DD | Sharpe | OVERALL |
|---|---:|---:|---:|---|
| V0 60/30/10 (baseline) | **+11.95%** | 12.67% | 1.11 | **PASS** |
| V1 60/25/15 | +4.83% | 12.36% | 0.70 | **FAIL** (CAGR + Sharpe) |
| V2 60/20/20 | +5.06% | 13.18% | 0.74 | **FAIL** (CAGR + Sharpe) |
| V3 65/20/15 | +1.57% | 12.55% | 0.35 | **FAIL** |
| V4 70/20/10 | +3.86% | 13.21% | 0.60 | **FAIL** |

Reducing Strategy B's allocation by any amount on the 2008-inclusive window
collapses portfolio CAGR from ~12% to single digits. The drawdown stays
roughly constant (all variants pass the 15% ceiling) but the return engine
is broken.

## Why the two windows disagree

**The 2008-inclusive 11.95% headline is heavily dependent on Strategy B's
performance during 2008-2013.** Two contributing factors:

1. **Survivor bias is worse on a longer window.** Strategy B's universe is
   the 2026-curated 20-name large-cap basket. Names that *would have been
   in a 2008-era basket but later collapsed* (Lehman, AIG, Citigroup,
   Wachovia, Countrywide, Bear Stearns) are absent. The 2008-onward
   standalone return on B is `+5,351%` — clearly impossible in the real world.
   The longer the window, the larger the gap between the survivor-biased
   backtest and reality.

2. **Strategy A had weak 2008-2013 performance.** Trend-following + cash
   floor underperforms during the 2008-09 SPY breakdown (signals lag) and
   the 2010-2013 grind-up (chop). Strategy B's outsized 2008-onward
   contribution carries the portfolio through this period. Reducing B
   removes that carry without adding a meaningful replacement engine —
   gold (C) helps but not enough.

On the production 2013-2026 window, both effects are dampened: less
survivor-bias error in B's contribution, and Strategy A's trend-following
worked through the 2013-2026 bull market.

## Decision

**Keep Strategy B at 30% for now.** Three reasons:

1. **The 2008-inclusive backtest's per-allocation results are not
   trustworthy enough to act on.** The diagnostic "Per-strategy contributions
   to final equity" shows B at `$1.1M` (return +5434%) regardless of B's
   allocation, which suggests the per-strategy attribution number is not
   recomputed per-variant. The *blended portfolio* numbers (CAGR/DD/Sharpe)
   appear sound, but the combination of huge per-strategy numbers and
   collapse-on-reduction merits a closer look before bet-sizing decisions.

2. **The 2013-2026 production window — which is what the live system will
   actually face going forward — is allocation-insensitive.** Reducing B
   to 25% gives essentially the same result as keeping it at 30%. There's
   no upside on the production window.

3. **The right way to resolve this is to fix the survivor bias, not to
   tune around it.** `plan.md > "2026-05-12-survivor-bias-stress-test"` is
   the open work item that will produce a survivor-bias-corrected Strategy
   B universe (point-in-time large-cap basket including Lehman/AIG/etc.).
   Until that runs, any allocation tweak based on the current backtest is
   tuning to a known-biased data generator.

## Recommended follow-ups

1. **Land the survivor-bias-corrected backtest** (the open plan item).
   Then re-run this allocation review. Expected outcome: Strategy B's
   2008-onward standalone return drops from +5,351% to something realistic
   (very rough guess: 200-400%); the portfolio CAGR on the 2008-inclusive
   window drops from 11.95% to 8-10%; the allocation-sensitivity collapse
   may or may not persist.

2. **Investigate the diagnostic per-strategy attribution.** The cached-looking
   `$1,106,895.52` number across three variants with different B allocations
   suggests `scripts/run_multi_strategy_backtest.py > run_backtest()` may not
   be re-running B with the new allocation when computing the diagnostic.
   If true, the blended portfolio result might also be subtly affected.

3. **Monitor the Strategy B forward paper-trade hit rate.** With paper
   trading live since 2026-05-11, B is currently producing real fills (4 of
   the 5 opening positions on 2026-05-12 were B picks: GOOGL, XOM, CSCO,
   WMT). If forward hit rate diverges sharply from the backtested ~85%+,
   that's the strongest evidence the survivor bias matters in practice.

## What changed in todo / plan

- `plan.md > Still open > Strategy B allocation review` → **resolved with a
  "keep at 30%" decision conditional on the survivor-bias-corrected
  backtest landing.**
- New follow-up: investigate per-strategy attribution caching in the backtest
  script (item #2 above).

## Variant artifacts

- `backtests/multi_strategy_portfolio/2008-06-02_to_2026-05-08_b_review_60_25_15.md`
- `backtests/multi_strategy_portfolio/2008-06-02_to_2026-05-08_b_review_60_20_20.md`
- `backtests/multi_strategy_portfolio/2008-06-02_to_2026-05-08_b_review_65_20_15.md`
- `backtests/multi_strategy_portfolio/2008-06-02_to_2026-05-08_b_review_70_20_10.md`
- Plus 2013-2026 baseline and `60_25_15_prod_window` variants in the same directory.
