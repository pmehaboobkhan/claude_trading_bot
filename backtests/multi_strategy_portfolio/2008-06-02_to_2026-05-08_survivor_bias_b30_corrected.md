# Multi-strategy backtest — 2008-06-02 → 2026-05-08

## Portfolio result
- Initial capital: $100,000.00
- Final equity: $183,900.02
- Total return: +83.90%
- **Annualized return: +3.46%**
- **Max drawdown: 12.44%**
- **Sharpe (rough): 0.60**
- Years: 17.91

## Allocations and per-strategy contribution
- Cash proxy: BIL (used for Strategy A cash floor and cash buffer)
- Cash buffer: 0% ($0 in BIL, static — no rebalancing)
- Deployed: $100,000

| Strategy | Allocation (of total) | Return | Final equity | Trades |
|---|---:|---:|---:|---:|
| dual_momentum_taa | 60.0% | +335.95% | $261,568.01 | 231 |
| large_cap_momentum_top5 | 30.0% | +3032.35% | $939,705.14 | 638 |
| gold_permanent_overlay | 10.0% | +390.65% | $49,064.74 | 1 |

## SPY buy & hold (context only — not a hurdle)
- Total return: +639.98%
- Annualized: +11.82%
- Max drawdown: 50.70%
- Sharpe: 0.66

## Absolute target evaluation
| Criterion | Result | Actual |
|---|---|---:|
| Annualized return ≥ 8.0% (low target) | FAIL | 3.46% |
| Annualized return ≥ 10.0% (high target) | FAIL | 3.46% |
| Max drawdown ≤ 15.0% | PASS | 12.44% |
| Sharpe ≥ 0.8 | FAIL | 0.60 |

**Overall: FAIL**

## Circuit-breaker
- Thresholds: FULL → HALF @ 8.0% DD, HALF → OUT @ 12.0% DD, HALF → FULL @ 5.0% DD, OUT → HALF @ 8.0% DD.
- Throttle events: 10 over the window.

| Date | From | To | Drawdown | Portfolio |
|---|---|---|---:|---:|
| 2008-09-30 | FULL | HALF | 10.21% | $95,624 |
| 2008-10-13 | HALF | OUT | 12.29% | $93,412 |
| 2020-03-04 | OUT | HALF | 7.97% | $98,017 |
| 2020-03-18 | HALF | OUT | 12.26% | $93,441 |
| 2023-10-02 | OUT | HALF | 8.00% | $97,985 |
| 2023-11-20 | HALF | FULL | 4.87% | $101,316 |
| 2024-08-07 | FULL | HALF | 8.11% | $119,371 |
| 2024-08-16 | HALF | FULL | 4.69% | $123,812 |
| 2026-02-02 | FULL | HALF | 9.54% | $188,945 |
| 2026-03-23 | HALF | OUT | 12.35% | $183,070 |

## Caveats
- Backtest uses yfinance survivor-biased current S&P 100 large-cap universe;
  large_cap_momentum_top5 results are optimistic for periods where losers were excluded.
- Includes ~4 bps round-trip friction (1bp slippage + 1bp half-spread per side).
- No tax modeling — real-world returns would be lower for short-term gains.
- 12-month momentum warmup means actual trading window is 252 days shorter than the calendar window.
- Circuit-breaker is post-hoc on daily returns: the throttle scales today's strategy-leg contribution to portfolio return; the cash leg earns BIL's daily return. This is an approximation — a true live circuit-breaker would execute rebalance trades on the day of the trigger and pay friction. Real-world results would be marginally worse (a few bps per transition).
