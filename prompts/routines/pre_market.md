# Pre-Market Routine — production prompt (v1)

> Triggered by Claude Code routine schedule at 06:30 ET, Mon–Fri. Use the `orchestrator` subagent.

You are running the **PRE-MARKET** routine for today's trading date (US/Eastern).

**v1 scope reminder**: This routine produces research output only. **No trade decisions in pre-market.** The deterministic signal evaluation runs in `end_of_day` for now (since v1 doesn't run a market-open routine yet — see `config/routine_schedule.yaml`). Pre-market's job is to surface today's regime, candidates, and risk posture.

## Steps

1. Comply with `CLAUDE.md`. **Capital preservation > clever trades. When uncertain, NO_TRADE.**
2. Mode check: read `config/approved_modes.yaml`. If `mode == HALTED`, write `logs/routine_runs/<ts>_halted.md`, notify, exit.
3. Schema validation: run `python tests/run_schema_validation.py`. Halt on any failure with a `logs/risk_events/` entry.
4. Load context:
   - `config/watchlist.yaml`, `config/risk_limits.yaml`, `config/strategy_rules.yaml`
   - Last 5 `journals/daily/*.md`
   - `trades/paper/positions.json` (if exists)
   - `memory/market_regimes/current_regime.md` (if exists)
   - `memory/symbol_profiles/*.md` for each watchlist symbol (if exists)
5. **Compute everything deterministically in Python**:
   ```bash
   python3 - <<'PY'
   import json
   from lib import data, signals, config
   symbols = [s["symbol"] for s in config.watchlist()["symbols"]]
   bars = {sym: data.get_bars(sym, timeframe="1Day", limit=250) for sym in symbols}
   # VIX is not in the watchlist but is useful for regime — fetch separately if you have a feed.
   # For free Alpaca IEX, VIX isn't available; signals.detect_regime handles vix_value=None.
   regime = signals.detect_regime(bars["SPY"], vix_value=None)
   sigs = signals.evaluate_all(bars, symbols, regime, config.strategy_rules())
   print(json.dumps({
       "regime": regime.__dict__,
       "signals": [s.__dict__ for s in sigs],
   }, default=str, indent=2))
   PY
   ```
   Capture the output. **All claims in the report must reference this JSON, not invented numbers.**

6. Dispatch in parallel (each agent gets the Python output as input):
   - `market_data` — write the raw `data/market/<date>/<HHMM>.json` snapshot.
   - `news_sentiment` — last 24h headlines per symbol + sector + macro.
   - `macro_sector` — adopt the regime classification from step 5 (do not re-derive); add narrative context.
   - `technical_analysis` — wrap the `signals` output with plain-English explanation.

7. Compose `reports/pre_market/<date>.md`. Required sections:
   - **Regime**: classification (from step 5), confidence, supporting indicators (cited), counter-evidence.
   - **Today's deterministic signals**: list every Signal with action ≠ NO_SIGNAL, plus the confirmations_passed and confirmations_failed verbatim.
   - **Top candidates** (max 5): for each ENTRY signal, 1-line bull thesis, 1-line bear thesis, R/R range (from `risk_limits.default_stop_loss_pct` / `default_take_profit_pct`), invalidation, what would change the read.
   - **Symbols on caution**: ETFs with a top-holding earnings event today/tomorrow.
   - **Open positions reminder**.
   - **Risk posture**: how much of daily-trade and position budget is available.

8. Append a `## Pre-market` section to today's `journals/daily/<date>.md`.

9. Compliance/Safety reviews the report. Any rule violation → halt; do not commit broken artifacts.

10. Commit: `pre-market: research report <date> (N candidates, regime=<x>)`.

11. Notify Telegram: "Pre-market <date>: regime=<x>, N entry signals. Top: <one line>. Report: <link>."

## Constraints (v1)
- **NO trade decisions** in this routine — only candidates and theses.
- **NO writes to** `config/`, `.claude/agents/`, `prompts/routines/`, `trades/live/*`.
- **NO fabrication.** Every numeric claim cites a `lib.signals` / `lib.indicators` output.
- **Subagent dispatches must stay ≤ `risk_limits.cost_caps.max_subagent_dispatches_per_routine`.**
