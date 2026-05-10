# Calm Turtle

Claude-native, routines-driven sector-ETF rotation paper-trading system.

> Slow, deliberate, defensive. Capital preservation > clever trades.

## What this is

A research-and-paper-trading system that:

- Uses **Claude Code routines** for scheduled pre-market, market-open, midday, pre-close, end-of-day, weekly, and monthly workflows.
- Trades a **12-symbol sector-ETF universe** (SPY + 11 GICS sector SPDRs) via the **Alpaca paper API**.
- Targets **risk-adjusted outperformance vs SPY** (Sharpe with drawdown ≤ SPY's), measured against two benchmarks: SPY and equal-weight buy-and-hold of the 11 sector ETFs.
- Persists every decision, journal, trade, and learning artifact in **Git** for full auditability.
- Runs a controlled **self-learning loop** that proposes prompt and strategy improvements but never silently changes risk, strategy, or trading-permission config.

## What this is NOT

- Not financial advice.
- Not a guaranteed-return system. Markets are risky; losses are possible.
- Not authorized to place live orders. v1 is research-only and paper-only.

## Operating modes

The current mode is in `config/approved_modes.yaml`:

- `RESEARCH_ONLY` — produces reports and decisions; no paper or live trades.
- `PAPER_TRADING` — simulates fills against decisions; updates paper log only.
- `LIVE_PROPOSALS` — produces live-trade proposals for human approval (Phase 6+).
- `LIVE_EXECUTION` — places live orders within hard limits (Phase 8+).
- `HALTED` — refuses all trading routines.

## Documentation

- [`plan.md`](plan.md) — full architecture and phased roadmap.
- [`todo.md`](todo.md) — implementation checklist with hard gates between phases.
- [`CLAUDE.md`](CLAUDE.md) — operating manual that the agents read on every run.
- [`docs/`](docs/) — operator runbook, incident response, model limitations, risk profile.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local  # then fill in your Alpaca + Telegram values
```

Secrets at runtime come from Claude Code routine env first, `.env.local` second. See `docs/operator_runbook.md`.
