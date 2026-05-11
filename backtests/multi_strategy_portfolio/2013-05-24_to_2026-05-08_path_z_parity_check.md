# Multi-strategy backtest — 2013-05-24 → 2026-05-08

## Portfolio result
- Initial capital: $100,000.00
- Final equity: $392,465.27
- Total return: +292.47%
- **Annualized return: +11.15%**
- **Max drawdown: 12.68%**
- **Sharpe (rough): 1.14**
- Years: 12.93

## Allocations and per-strategy contribution
- Cash buffer: 0% ($0 in SHV, static — no rebalancing)
- Deployed: $100,000

| Strategy | Allocation (of total) | Return | Final equity | Trades |
|---|---:|---:|---:|---:|
| dual_momentum_taa | 60.0% | +219.90% | $191,942.39 | 163 |
| large_cap_momentum_top5 | 30.0% | +1857.05% | $587,115.60 | 367 |
| gold_permanent_overlay | 10.0% | +221.92% | $32,192.34 | 1 |

## SPY buy & hold (context only — not a hurdle)
- Total return: +457.94%
- Annualized: +14.22%
- Max drawdown: 33.72%
- Sharpe: 0.87

## Absolute target evaluation
| Criterion | Result | Actual |
|---|---|---:|
| Annualized return ≥ 8.0% (low target) | PASS | 11.15% |
| Annualized return ≥ 10.0% (high target) | PASS | 11.15% |
| Max drawdown ≤ 15.0% | PASS | 12.68% |
| Sharpe ≥ 0.8 | PASS | 1.14 |

**Overall: PASS**

## Circuit-breaker
- Thresholds: FULL → HALF @ 8.0% DD, HALF → OUT @ 12.0% DD, HALF → FULL @ 5.0% DD, OUT → HALF @ 8.0% DD.
- Throttle events: 15 over the window.

| Date | From | To | Drawdown | Portfolio |
|---|---|---|---:|---:|
| 2018-02-08 | FULL | HALF | 9.37% | $192,595 |
| 2018-03-12 | HALF | FULL | 4.99% | $201,898 |
| 2018-03-22 | FULL | HALF | 8.75% | $193,910 |
| 2018-07-24 | HALF | FULL | 4.98% | $201,914 |
| 2018-10-11 | FULL | HALF | 8.78% | $193,846 |
| 2019-06-19 | HALF | FULL | 4.99% | $201,904 |
| 2020-02-25 | FULL | HALF | 8.78% | $265,478 |
| 2020-03-05 | HALF | OUT | 12.41% | $254,914 |
| 2023-10-26 | OUT | HALF | 8.00% | $267,763 |
| 2023-11-14 | HALF | FULL | 4.18% | $278,872 |
| 2024-07-24 | FULL | HALF | 9.00% | $380,351 |
| 2024-08-05 | HALF | OUT | 12.68% | $364,986 |
| 2025-10-10 | OUT | HALF | 7.99% | $384,570 |
| 2026-01-27 | HALF | FULL | 4.70% | $398,318 |
| 2026-03-18 | FULL | HALF | 8.39% | $382,909 |

## Caveats
- Backtest uses yfinance survivor-biased current S&P 100 large-cap universe;
  large_cap_momentum_top5 results are optimistic for periods where losers were excluded.
- Includes ~4 bps round-trip friction (1bp slippage + 1bp half-spread per side).
- No tax modeling — real-world returns would be lower for short-term gains.
- 12-month momentum warmup means actual trading window is 252 days shorter than the calendar window.
- Circuit-breaker is post-hoc on daily returns: the throttle scales today's strategy-leg contribution to portfolio return; the cash leg earns SHV's daily return. This is an approximation — a true live circuit-breaker would execute rebalance trades on the day of the trigger and pay friction. Real-world results would be marginally worse (a few bps per transition).
