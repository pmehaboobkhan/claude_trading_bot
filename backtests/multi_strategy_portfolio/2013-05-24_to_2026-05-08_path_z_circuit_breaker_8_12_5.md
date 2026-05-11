# Multi-strategy backtest — 2013-05-24 → 2026-05-08

## Portfolio result
- Initial capital: $100,000.00
- Final equity: $273,323.41
- Total return: +173.32%
- **Annualized return: +8.09%**
- **Max drawdown: 12.69%**
- **Sharpe (rough): 0.95**
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
| Annualized return ≥ 8.0% (low target) | PASS | 8.09% |
| Annualized return ≥ 10.0% (high target) | FAIL | 8.09% |
| Max drawdown ≤ 15.0% | PASS | 12.69% |
| Sharpe ≥ 0.8 | PASS | 0.95 |

**Overall: PASS**

## Circuit-breaker
- Thresholds: HALF @ 8.0% DD, OUT @ 12.0% DD, recover @ 5.0% DD (hysteresis: OUT → HALF → FULL).
- Throttle events: 12 over the window.

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
| 2024-06-12 | OUT | HALF | 4.99% | $276,514 |
| 2024-06-13 | HALF | FULL | 4.74% | $277,240 |
| 2024-07-24 | FULL | HALF | 9.02% | $264,796 |
| 2024-08-05 | HALF | OUT | 12.69% | $254,100 |

## Caveats
- Backtest uses yfinance survivor-biased current S&P 100 large-cap universe;
  large_cap_momentum_top5 results are optimistic for periods where losers were excluded.
- Includes ~4 bps round-trip friction (1bp slippage + 1bp half-spread per side).
- No tax modeling — real-world returns would be lower for short-term gains.
- 12-month momentum warmup means actual trading window is 252 days shorter than the calendar window.
- Circuit-breaker is post-hoc on daily returns: the throttle scales today's strategy-leg contribution to portfolio return; the cash leg earns SHV's daily return. This is an approximation — a true live circuit-breaker would execute rebalance trades on the day of the trigger and pay friction. Real-world results would be marginally worse (a few bps per transition).
