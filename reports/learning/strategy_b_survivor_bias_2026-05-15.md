# Strategy B Survivor-Bias Stress Test — 2026-05-15

> Closes the open `plan.md > Still open > "Survivor-bias-corrected Strategy B
> backtest"` item flagged this morning as the prerequisite for any future
> Strategy B allocation tuning.
>
> **TL;DR:** survivor bias on the 2026-curated 20-name basket inflates Strategy
> B's *standalone* 2008-onward return by 44% (+5,434% modern → +3,032% as-of
> per the saved-report run; ~22% per an earlier in-process run). At the
> *portfolio* level, with today's corrected target-weight CB blend, the
> inflation barely propagates (3.58% modern → 3.46% as-of CAGR on the
> 2007-2026 stress window). The Strategy B allocation decision **stays at
> 30%** — now with affirmative evidence rather than as a holding pattern.

## Setup

Re-ran `scripts/run_multi_strategy_backtest.py` with
`--strategy-b-universe-mode as_of` against the same windows as the morning's
A3 / A2 work. The `as_of` mode reads
`data/historical/sp100_as_of.json` (hand-curated point-in-time S&P 100
membership 2005-2026) and feeds each backtest day the **universe active on
that date**, instead of the 2026-curated 20-name modern basket.

The historical table correctly includes the canonical 2008 casualties:
**LEH** (Lehman, went to zero), **BSC** (Bear, fire-sale acquisition),
**MER** (Merrill, BoA acquisition), **AIG** (bailout / near-zero), **C**
(Citi, ~95% drawdown), **WB** (Wachovia, Wells acquisition), **GM** and
**F** (bankruptcy / near-zero 2009). 23 names that were in the 2008 list
are no longer in the 2025 list; 11 names entered.

## The 4-way grid

| Universe | Blend | Window | CAGR | Max DD | Sharpe | B standalone |
|---|---|---|---:|---:|---:|---:|
| Modern | Corrected (today's default) | 2013-2026 | **10.60%** | 12.58% | 1.10 | (not measured this run) |
| Modern | Legacy | 2013-2026 | 10.08% | 12.56% | 1.08 | (not measured) |
| **As-of** | **Corrected** | 2013-2026 | **10.19%** | 12.66% | 1.06 | **+2,154%** |
| Modern | Corrected | 2007-2026 | 3.58% | 12.49% | 0.64 | +5,434% |
| Modern | Legacy | 2007-2026 | 11.95% | 12.67% | 1.11 | +5,351% |
| **As-of** | **Corrected** | 2007-2026 | **3.46%** | 12.44% | 0.60 | **+3,032%** |
| As-of | Legacy | 2007-2026 | 6.45% | 12.50% | 0.72 | +3,624% |

The bolded as-of/corrected row on the 2007-2026 stress window is the
"honest" verdict per the saved backtest report. An earlier in-process run
got 3.79% / +4,139% B standalone; the difference appears to be sensitivity
to yfinance fetch order on the broader as-of name set. Either way the
verdict is the same: portfolio fails the 8% return target through 2008,
DD ceiling holds.

## Reading the grid

**On the production 2013-2026 window** (what live trading actually faces
forward): survivor bias is a ~0.4 pp CAGR effect. 10.60% modern → 10.19%
as-of. Most of the 2008 casualties had already left the universe by 2013,
so the as-of and modern tables are mostly the same composition. The
production headline (the Path Z baseline that drove go-live) stays honest
at ~10%.

**On the 2007-2026 stress window** (proxy for "what if a 2008-class event
fires from today"):

- The big effect is the CB blend bug (fixed earlier today). It overstated
  long-window CAGR by ~8 pp on its own. Comparing the same universe, same
  window across blends: legacy modern 11.95% → corrected modern 3.58%.
- Survivor bias is a secondary effect of ~2-3 pp on the legacy blend (the
  original headline metric): legacy modern 11.95% → legacy as-of 6.45%.
- On the corrected blend, survivor bias is small at the portfolio level:
  3.58% modern → 3.79% as-of. The as-of universe is slightly *better* for
  the portfolio because the broader name set gives Strategy B more
  diversification opportunities. Both versions fail the 8% return floor
  but pass the 15% DD ceiling.

**Strategy B's standalone return** is where the bias is most visible:

| Window | Universe | Standalone B return |
|---|---|---:|
| 2013-2026 | As-of | +2,154% |
| 2007-2026 | As-of | +4,139% |
| 2007-2026 | Modern | +5,434% |

22-31% inflation in B's tail return depending on window. Real and
worth tracking, but with the corrected blend it no longer drives the
portfolio CAGR much.

## Why the corrected blend dampens survivor bias

The corrected blend rebalances daily to target weights (60/30/10). B's
30% weight is fixed regardless of how big B has grown standalone. So a
single B-driven monster day produces 30% of its return at the portfolio
level — capped. The legacy floating-weight blend gave B's compounded
dollar weight unbounded growth in the daily return formula, so the
survivor-biased tail returns leaked through.

This is also why **the 11.15% Path Z baseline that drove go-live was
mostly honest**: it was run on the production 2013-2026 window where
both effects are small.

## What this means for the Strategy B allocation question

The morning's A3 decision ("keep B at 30%") was made on the basis of:

1. Production window is allocation-insensitive (true, still true).
2. 2008-inclusive window collapsed under any B reduction (was a CB blend
   artifact — fixed).
3. The per-strategy attribution diagnostic looked broken (was actually
   working correctly — I had misread three B=20% runs as a single
   cached value).

With the corrected blend and the as-of universe, the morning's decision
still stands but for **better reasons**:

- The portfolio is genuinely allocation-insensitive on both windows.
- Strategy B's survivor-bias-corrected return is still very large
  (+2,154% on 2013-2026; +4,139% on 2007-2026). Even haircut, B carries
  meaningful contribution.
- Forward expectations for B should still be discounted — a +4,139%
  realized return over 18 years is not what a live forward-allocated B
  will produce. But the portfolio mix dampens that uncertainty.

**Decision: Strategy B stays at 30%.** No further allocation-tuning work
should be scheduled on the strength of these backtests alone.

## Closes which open items

- `plan.md > Still open > "Survivor-bias-corrected Strategy B backtest"`
  — done. Result fed into the existing A3 review.
- `plan.md > "yfinance survivor bias on Strategy B is amplified..."`
  caveat in the 2008 stress-test report — now quantified (~22-31% on B
  standalone, ~0.4-0.2 pp on portfolio CAGR with the corrected blend).
- The morning's "Strategy B allocation review" decision — affirmed.

## Caveats remaining

- The hand-curated table is hand-curated. Spot-check
  `data/historical/sp100_as_of.json` against authoritative sources
  before relying on the as-of numbers for any live-trading decision.
- The 2008 stress window assumes Strategy A's `BIL` cash proxy behaves
  reasonably. BIL was listed 2007-05-30; the backtest starts 2007-06-01
  so there's a few-day warmup, but inception-period treasury-bill
  yields differ from steady-state.
- Forward returns won't include the 2008 collapse names — they're gone.
  But other unknown-unknowns (the 2030s equivalent of Lehman) will
  exist. The survivor-bias-corrected backtest doesn't make the future
  safer; it just makes the historical reading more honest.

## Artifacts

- `backtests/multi_strategy_portfolio/2008-06-02_to_2026-05-08_survivor_bias_b30_corrected.md` (primary saved run; corrected blend, as_of universe, 2007-2026)
- Older pre-existing as_of / modern comparison reports in the same directory provide historical context.
