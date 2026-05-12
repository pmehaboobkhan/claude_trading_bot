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
   - Last 5 `memory/daily_snapshots/<date>.md` files (one-paragraph summaries written by end_of_day — ~1 KB each, replaces reading full daily journals which can grow to 50+ KB).
   - `trades/paper/positions.json` (if exists)
   - `memory/market_regimes/current_regime.md` (if exists)
   - `memory/symbol_profiles/*.md` for each watchlist symbol (if exists)
5. **Compute everything deterministically in Python**:
   ```bash
   python3 - <<'PY'
   import json
   from lib import data, signals, config
   symbols = [s["symbol"] for s in config.watchlist()["symbols"]]
   bars = {sym: data.get_bars(sym, timeframe="1Day", limit=300) for sym in symbols}
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

## Composing the Telegram notification

The routine commits to a `claude/...` feature branch (Claude Code default).
A GitHub Action immediately fast-forward-merges that branch into `main`
and deletes the source branch (see `.github/workflows/auto_merge_claude.yml`).

This means: **by the time the user reads your Telegram message, the feature
branch no longer exists**. Never reference the feature branch by name in the
notification.

Compose links as follows:

- **Artifacts**: link to the file on the `main` branch using the form
  `https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/<path>`.
  These URLs resolve as soon as the auto-merge completes (~30 seconds after
  your push) and remain stable forever.
- **Commits**: cite the short SHA (e.g. `d10f9b6`). Do **not** suffix it
  with "on claude/<branch>" — commit SHAs are independent of branch refs
  and remain valid after the feature branch is deleted. If you want a
  clickable link, use `https://github.com/pmehaboobkhan/claude_trading_bot/commit/<sha>`.
- **Status**: it is fine to say "auto-merged to main" or to omit branch
  information entirely. Do not mention the feature branch name.

Example for pre_market:

```
[Calm Turtle] Pre-market 2026-05-12
Regime: range_bound (low confidence)
7 ENTRY signals; top candidate GLD (Strategy A + C agree)
Commit: d10f9b6 (auto-merged to main)
Report: https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/reports/pre_market/2026-05-12.md
Journal: https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/journals/daily/2026-05-12.md
```

## Routine audit log (mandatory final step)

Before exiting (clean OR halted OR error), write one audit file via
`lib.routine_audit`:

```bash
python3 - <<'PYAUDIT'
from lib import routine_audit
audit = routine_audit.RoutineAudit(
    routine="<routine_name_snake_case>",
    started_at="<ISO start ts>",
    ended_at="<ISO end ts>",
    duration_seconds=<float>,
    exit_reason=<"clean"|"halted"|"error"|"noop">,
    files_read=[
        routine_audit.file_record(p)
        for p in [<list of absolute paths you Read during this run>]
    ],
    subagent_dispatches={"<agent>": <count>, ...},
    artifacts_written=[<list of repo-relative paths you Wrote>],
    commits=[<short SHAs you created>],
    notes="<one-line context: anything noteworthy>",
)
routine_audit.write_audit(audit)
PYAUDIT
```

Why this exists: this is the only observable view of context-budget usage
across routine runs. `approximate_input_kb` is a proxy for input-token cost
and is trended over time. If it starts growing without bound, that's the
signal to compress per-symbol histories or rotate memory files. Until then,
we trust the system.

The hook-written `_start.md` / `_end.md` markers are separate and unchanged.
