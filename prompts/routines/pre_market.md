# Pre-Market Routine — production prompt

> Triggered by Claude Code routine schedule at 06:30 ET, Mon–Fri. Use the `orchestrator` subagent.

You are running the **PRE-MARKET** routine for today's trading date (US/Eastern).

1. Comply with `CLAUDE.md`. **Capital preservation > clever trades. When uncertain, NO_TRADE.**
2. Mode check: read `config/approved_modes.yaml`. If `mode == HALTED`, write `logs/routine_runs/<ts>_halted.md`, notify, exit.
3. Schema validation: run `python tests/run_schema_validation.py`. Halt on any failure with a `logs/risk_events/` entry.
4. Load context: `config/watchlist.yaml`, `config/risk_limits.yaml`, `config/strategy_rules.yaml`, the last 5 `journals/daily/*.md`, `trades/paper/positions.json`, `memory/market_regimes/current_regime.md`, `memory/symbol_profiles/*.md`.
5. Dispatch in parallel:
   - `market_data` — overnight quotes for the 12 watchlist symbols + SPY + VIX, plus daily bars for indicators.
   - `news_sentiment` — last 24h headlines per symbol + sector + macro.
   - `macro_sector` — propose today's market regime classification.
   - `technical_analysis` — full TA per symbol, including RS rank vs SPY (20d, 60d).
6. Compose `reports/pre_market/<date>.md`. Required sections:
   - **Regime**: classification, confidence, ≥3 supporting indicators, counter-evidence.
   - **Top candidates** (max 5): for each, 1-line bull thesis, 1-line bear thesis, R/R range, invalidation, what would change the read.
   - **Symbols on caution**: which ETFs have a top-holding earnings event today/tomorrow.
   - **What I am NOT going to trade today**: at least 3 symbols with explicit reasons.
   - **Open positions reminder**.
   - **Risk posture**: how much of daily-trade and position budget is available.
7. Append a `## Pre-market` section to today's `journals/daily/<date>.md`.
8. Compliance/Safety reviews the report. Any rule violation → halt routine; do not commit broken artifacts.
9. Commit with message: `pre-market: research report <date> (N symbols flagged)`.
10. Notify Telegram: "Pre-market <date>: regime=<x>, candidates=<n>. Top thesis: <one line>. Report: <link>."

**Constraints**:
- NO trade decisions in this routine — only candidates and theses. Trade decisions happen at market open.
- NO writes to `config/`, `prompts/agents/` (or `.claude/agents/`), `prompts/routines/`, `trades/live/*`.
- NO fabrication. Every claim cites a source or indicator.
