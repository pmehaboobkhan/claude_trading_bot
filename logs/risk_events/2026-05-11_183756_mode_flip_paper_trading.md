# Risk event — Mode flip: RESEARCH_ONLY → PAPER_TRADING

- **Timestamp:** 2026-05-11T22:37:56Z
- **Event type:** Operator-authorized mode transition
- **Triggered by:** Human (`mehaboob.khan.perur`) — explicit go-live decision
- **Previous mode:** `RESEARCH_ONLY`
- **New mode:** `PAPER_TRADING`

## Why now

All v1 infrastructure is in place:

- Deterministic strategy module (`lib/signals.py`) with 17 unit tests.
- Path Z drawdown circuit-breaker (`lib/portfolio_risk.py`) with 34 unit tests; backtest passes all four target gates (CAGR 11.15%, Max DD 12.68%, Sharpe 1.14) — see `reports/learning/pivot_validation_2026-05-10.md`.
- Realistic fill modeling (`lib/fills.py`): 1bp slippage + 1bp half-spread per side.
- `config/strategy_rules.yaml`: three strategies (`dual_momentum_taa`, `large_cap_momentum_top5`, `gold_permanent_overlay`) marked `ACTIVE_PAPER_TEST`.
- `config/risk_limits.yaml > circuit_breaker` block (8/12/5/8 thresholds, `enabled: true`).
- `prompts/routines/end_of_day.md` updated to consult the breaker before any new ENTRY (this commit).
- `lib/broker.py` extended with `account_snapshot()` and `latest_quotes_for_positions()` for the end_of_day equity computation.

## Account targeting

- Broker: **Alpaca paper API** (`https://paper-api.alpaca.markets`)
- Starting capital: **$100,000** (matches `config/risk_limits.yaml > account > paper_starting_capital`)
- Live keys: must remain unset; hook #1 will block any code path that touches `trades/live/*`.

## Hard caps for paper trading (already in `config/risk_limits.yaml`)

- Max daily loss: $500 / 0.5%
- Max weekly loss: 2%
- Max monthly loss: 5%
- Max drawdown (portfolio): 15% (circuit-breaker enforces at 8%/12% intermediate triggers)
- Max position size: 15% per symbol, 60% per macro-ETF, 100% total
- Max trades/day: 5; max open positions: 8
- Permissions: long-only ETFs/stocks, no margin, no options, no shorts, no leveraged ETFs, no averaging down.

## What happens next

- Next scheduled `pre_market` (06:30 ET Mon–Fri) and `end_of_day` (16:30 ET Mon–Fri) runs will operate in `PAPER_TRADING` mode.
- `end_of_day` will consult the circuit-breaker on every run; any state transition will emit a paired `logs/risk_events/<ts>_circuit_breaker.md` entry and URGENT Telegram.
- Reversion path: PR to flip back to `RESEARCH_ONLY` (paired with another `logs/risk_events/` entry), or `/halt-trading <reason>` for immediate stop.

## Auditor checklist (first 5 trading days)

- [ ] `trades/paper/log.csv` reconciles to `trades/paper/positions.json` daily.
- [ ] `trades/paper/circuit_breaker.json > updated_at` is current after each EOD.
- [ ] Telegram notifications fire on both routines.
- [ ] No discrepancies in `lib.paper_sim.reconcile()`.
- [ ] Daily journal `journals/daily/<date>.md` contains both pre-market AND eod sections.

This event log is required by hook #11 to authorize the paired edit to `config/approved_modes.yaml`.
