# Risk Profile — Calm Turtle

> **Status:** Phase 0 deliverable. This file is the human-signed ground truth on what risk the system is permitted to take. It mirrors the limits encoded in `config/risk_limits.yaml`, the strategies in `config/strategy_rules.yaml`, and the operating rules in `CLAUDE.md`. Any change to live trading scope requires a PR that also updates this file.

**Last reviewed:** 2026-05-14 (rewritten after 2026-05-10 pivot to multi-strategy retail portfolio; sector-rotation framing rejected)
**Trading mode at write time:** `PAPER_TRADING` (per `config/approved_modes.yaml`)
**Goal:** absolute return, 8–10% CAGR / max DD ≤ 15% / Sharpe ≥ 0.8

---

## 1. Capital at risk

| Account | Notional | Source |
|---|---|---|
| Paper (Alpaca paper API) | $100,000 | `config/risk_limits.yaml > account.paper_starting_capital` |
| Live (Alpaca live API)   | $0       | `config/risk_limits.yaml > account.live_starting_capital` |

Live capital remains $0 until **all** of: Phase 8 unlock criteria met (§6), explicit human PR, and a signed update to this document.

## 2. Goal

The system targets an **absolute return** band, not a relative one:

- **8–10% CAGR** annualized compound return over rolling periods.
- **Max drawdown ≤ 15%** of peak portfolio equity.
- **Sharpe ratio ≥ 0.8** once N ≥ 30 closed trades or ≥ 90 trading days.

SPY return is reported alongside in weekly/monthly reviews **for context only**. The system does not have to beat any index. The goal is reliable absolute return with bounded drawdown.

This is not an income guarantee. Markets are risky. Even diversified multi-strategy portfolios have negative quarters.

## 3. Strategies and allocations

| Strategy | Allocation | Status | Rationale |
|---|---|---|---|
| `dual_momentum_taa` | 60% | `ACTIVE_PAPER_TEST` | Antonacci-style cross-asset trend across SPY/IEF/GLD with SHV cash floor. Best historical Sharpe of the three; absorbs equity-bond regime shifts. |
| `large_cap_momentum_top5` | 30% | `ACTIVE_PAPER_TEST` | Top-5 large-caps by 6-month return, gated by SPY > 10-month SMA. Adds equity beta when trend supports it. Survivor-bias caveat noted — see §7. |
| `gold_permanent_overlay` | 10% | `ACTIVE_PAPER_TEST` | Permanent GLD allocation. Diversifier with near-zero correlation to equities and bonds; crisis hedge. |

When `dual_momentum_taa` and `gold_permanent_overlay` both signal ENTRY on GLD, the higher-allocation strategy (TAA, 60%) is primary and the overlay's allocation is **subsumed** rather than double-booked. Determinism lives in `lib/signal_consolidator.py`.

The four sector-rotation strategies in `config/strategy_rules.yaml > allowed_strategies` are marked `REJECTED` and may never execute. They remain in the file for audit trail only.

## 4. Loss tolerances (from `config/risk_limits.yaml`)

| Limit | Value | Field |
|---|---|---|
| Max daily loss | $500 / 0.5% of equity | `limits.max_daily_loss_usd` / `limits.max_daily_loss_pct` |
| Max weekly loss | 2.0% | `limits.max_weekly_loss_pct` |
| Max monthly loss | 5.0% | `limits.max_monthly_loss_pct` |
| Max drawdown | 15.0% | `limits.max_drawdown_pct` |
| Max single-position | 15.0% of equity | `limits.max_position_size_pct` |
| Max macro-ETF position | 60.0% (SPY/IEF/GLD only) | `limits.max_macro_etf_position_pct` |
| Max risk per trade | 1.5% of equity | `limits.max_risk_per_trade_pct` |
| Daily drawdown halt | -2.0% | `limits.daily_drawdown_halt_pct` |
| Max trades per day | 5 | `limits.max_trades_per_day` |
| Max open positions | 8 | `limits.max_open_positions` |
| Default stop loss | 10.0% | `limits.default_stop_loss_pct` |
| Default take profit | 25.0% | `limits.default_take_profit_pct` |
| Minimum R/R | 1.5 | `limits.minimum_risk_reward` |

Prohibited (`config/risk_limits.yaml > permissions`): margin, options, short selling, leveraged ETFs, averaging down. All `false`.

## 5. Halt triggers

The monthly review routine **must** recommend `STAY_PAPER` or `HALT_AND_REVIEW` if any of the following holds (per `CLAUDE.md > Performance tracking`):

- Portfolio drawdown breaches **12%** (act before the 15% hard cap).
- 3-month rolling return is **negative**.
- Any individual strategy's drawdown breaches **25%** of its allocated capital.

Operational kill switches:

- `/halt-trading <reason>` flips `config/approved_modes.yaml > mode` to `HALTED` with a paired audit log. Resume requires a human PR.
- `/enter-safe-mode <reason>` keeps the deterministic engine running but suppresses every learning write (`memory/`, `prompts/proposed_updates/`, self-learning agent). Use when the LLM stack is degraded but the strategy is still trustworthy.
- Daily P&L hits −2% → trading halts for the day (`limits.daily_drawdown_halt_pct`).
- 3 consecutive losses → halt with 1-day cool-off (`halts.halt_after_consecutive_losses` + `halts.cool_off_days_after_halt`).

Portfolio-level circuit-breaker (Path Z, `config/risk_limits.yaml > circuit_breaker`):

- FULL → HALF at 8% portfolio drawdown.
- HALF → OUT at 12% portfolio drawdown.
- HALF → FULL when DD ≤ 5% (3pp hysteresis).
- OUT → HALF when DD ≤ 8% (4pp hysteresis).

The circuit-breaker throttles new ENTRIES only. EXITs are never throttled — reducing risk is always allowed.

## 6. Live-trading unlock criteria

All of the following must hold before a human PR may set `config/approved_modes.yaml > mode: LIVE_EXECUTION`:

**Floor criteria:**
- 90+ trading days of paper operation.
- 30+ closed paper trades across all strategies.
- Portfolio Sharpe ratio ≥ 0.8 on paper data.
- Max drawdown ≤ 12% on paper data.
- Explicit human PR + signed update to this document.

**Regime-diversity gates** (`config/risk_limits.yaml > gates.regime_diversity_gates`):
- At least one circuit-breaker throttle event observed (FULL→HALF or HALF→OUT).
- At least one SPY 10-month-SMA trend flip during the window.
- At least one daily VIX close ≥ 25 observed.
- At least 4 distinct calendar months of operation.

Evaluated by `lib.live_trading_gate.evaluate_gates()` during the monthly review. The verdict is a recommendation input only — the human PR-approval requirement is non-negotiable.

## 7. Known limitations

- **Survivor-bias in Strategy B:** the large-cap universe in `config/watchlist.yaml` was selected from current S&P-100 membership. Backtest CAGR is overstated by an estimated ~7.25 pp/yr at the portfolio level (2007–2026 window). Plan-level discussion in `plan.md > "Survivor bias caveat"`. May require allocation reduction; see `plan.md > "Strategy B allocation review"`.
- **2008 stress test pending:** the multi-strategy backtest starts 2013-05 (META IPO constraint). The system has not been tested against the 2008 financial crisis. Real recession drawdowns could exceed the 12.68% backtest figure. The 2015 max-DD reading should be treated as a lower bound.
- **VIX data absent on Alpaca free tier:** `vix_high_observed` regime-diversity gate will permanently fail until a VIX-capable feed is wired (paid Alpaca, Polygon, Tiingo). This is intentional — the system must demonstrate it has seen elevated volatility before live unlock is permitted.
- **Daily-bar staleness on Alpaca IEX:** daily bars lag 6–19 days behind real time. Hybrid yfinance + Alpaca path is the documented mitigation; not yet wired into the routines.

## 8. Tax considerations

- This system does **not** optimize for taxes. Wash-sale rules apply on live trading.
- Annual export of `trades/paper/log.csv` (and the live equivalent once Phase 8 opens) is the operator's responsibility.
- A CPA must review the position-keeping approach before live mode is enabled.

## 9. Operator acknowledgement

By signing this document the operator acknowledges:

1. The capital, limits, and unlock criteria above are the **only** scope under which the system is permitted to operate.
2. Paper-trading results do not predict live-trading results. Slippage, partial fills, liquidity, taxes, and broker-side rejections all degrade live performance in ways paper simulation cannot fully model.
3. The system **may lose money**, including in live mode. The 15% drawdown cap is a *halt trigger*, not a guarantee that losses stay below 15%.
4. Live execution will not be enabled without a human PR that updates the "Last reviewed" date and adds a signed note in the changelog below.

---

## Changelog

- **2026-05-14** — rewritten for the multi-strategy retail portfolio (post-pivot). Sector-rotation framing and the SPY-relative goal removed. Goal is now absolute return: 8–10% CAGR / max DD ≤ 15% / Sharpe ≥ 0.8. System in `PAPER_TRADING` mode. No live capital authorized.
- 2026-05-09 — initial Phase 0 placeholder (since superseded by the 2026-05-14 rewrite).

## Sign-off

- Operator: _<pending signature on PR merge>_
- Date: _<pending>_
