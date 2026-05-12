# Market Open Routine — production prompt (v1, monitoring-only)

> Scheduled 09:35 ET, Mon–Fri (5 minutes after open). Use the `orchestrator` subagent. **Monitoring routine — does NOT open new positions.**

## v1 scope
The market_open routine is a **monitoring layer**, not an entry-generating layer. Entries happen only at EOD against closing prices — that is where our backtest evidence lives. The job here is to:

1. Refresh circuit-breaker state with opening equity (in case overnight news moved the portfolio meaningfully).
2. Detect overnight gaps that breached an open position's stop or take-profit.
3. Propose `PAPER_CLOSE` for any position with an invalidation trigger.
4. **NEVER call `paper_sim.open_position()`.** ENTRY signals from `lib.signals` are ignored in this routine.

## Steps

1. Comply with `CLAUDE.md`. When uncertain, NO_TRADE.
2. Mode check: read `config/approved_modes.yaml`. If `HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit.
3. Schema validation: run `python3 tests/run_schema_validation.py`.
4. Load: `trades/paper/positions.json`, `trades/paper/circuit_breaker.json` (if exists), today's `reports/pre_market/<date>.md`, last 5 daily journals.
5. **Fetch opening quotes** for every open position only (not the whole watchlist):
   ```bash
   python3 - <<'PYQUOTES'
   import json
   from lib import broker
   acct = broker.account_snapshot()
   quotes = broker.latest_quotes_for_positions()
   print(json.dumps({
       "cash": acct["cash"],
       "equity": acct["equity"],
       "buying_power": acct["buying_power"],
       "quotes": quotes,
   }, indent=2))
   PYQUOTES
   ```
   If no open positions exist, skip to step 9.
6. **Circuit-breaker refresh**:
   ```bash
   python3 - <<'PYCB'
   import json
   from lib import config, paper_sim, portfolio_risk
   risk_cfg = config.risk_limits()
   cb_cfg = risk_cfg.get("circuit_breaker", {})
   thresholds = portfolio_risk.from_config(cb_cfg)
   # equity from step 5
   equity = ...   # paper_sim.portfolio_equity(quotes, cash_balance=acct["cash"])
   result = portfolio_risk.advance(equity, thresholds)
   print(json.dumps({
       "state": result.new_state.state,
       "previous_state": result.previous_state,
       "drawdown_pct": round(result.drawdown * 100, 2),
       "transitioned": result.transitioned,
   }, indent=2))
   PYCB
   ```
   If `result.transitioned` is true → write `logs/risk_events/<ts>_circuit_breaker.md`, notify URGENT Telegram.
7. **Health check on every open position** via `lib.portfolio_health`:
   ```bash
   python3 - <<'PYHEALTH'
   import json
   from lib import portfolio_health
   healths = portfolio_health.assess_positions(quotes)   # quotes from step 5
   to_close = [portfolio_health.health_as_dict(h) for h in healths if h.should_close()]
   print(json.dumps(to_close, indent=2))
   PYHEALTH
   ```
   For any position with `invalidation_triggers` non-empty:
   - `trade_proposal` wraps as a `PAPER_CLOSE` decision file at `decisions/<date>/<HHMM>_<SYM>.json`. Include `invalidation_triggers` verbatim in the decision JSON.
   - `risk_manager` verifies the position exists and the close is appropriate.
   - `compliance_safety` final gate.
   - On approval (and `mode == PAPER_TRADING`), call `lib.paper_sim.close_position(symbol, quote_price=<current>, rationale_link=<decision_file>)`.
8. `lib.paper_sim.reconcile()` — discrepancy → `logs/risk_events/<ts>_reconcile.md` + URGENT notify.
9. Append a `## Market open` section to today's `journals/daily/<date>.md` summarising: opening equity, CB state, any closes proposed/executed, any gap flags.
10. **Commit only if anything actionable happened** (close, circuit-breaker transition, risk event). If routine was pure no-op, write `logs/routine_runs/<ts>_market_open_noop.md` and skip the commit.
11. Notify Telegram only if action was taken.

## Constraints (hard rules)
- **No new entries.** Ignore ENTRY signals from `lib.signals`. If you find yourself drafting a PAPER_BUY decision in market_open, stop — that's a bug.
- **EXITs are never throttled by the circuit-breaker** — closing reduces risk and always proceeds if invalidation is real.
- Subagent dispatches ≤ `risk_limits.cost_caps.max_subagent_dispatches_per_routine`.
- NO live execution.

## Why monitoring-only
Our three v1 strategies (`dual_momentum_taa`, `large_cap_momentum_top5`, `gold_permanent_overlay`) all operate on daily bars and use slow signals (12-month momentum, 10-month SMA). They emit ENTRY/EXIT only on closing prices — that's what the backtest validated. Adding intraday entries would compound risk we have no evidence for. The monitoring job is real: catching overnight gaps that breached a stop, and refreshing the circuit-breaker before midday.


## Composing the Telegram notification

This routine commits to a `claude/...` feature branch (Claude Code default).
A GitHub Action immediately fast-forward-merges that branch into `main`
and deletes the source branch (see `.github/workflows/auto_merge_claude.yml`).
By the time the user reads your Telegram message, the feature branch no
longer exists.

- Artifact links: use `https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/<path>`.
- Commits: cite the short SHA only. Do not suffix with the branch name.
- Status: "auto-merged to main" or omit branch info.
- Notify only if action was taken (a close, a risk event, a regime call) — pure no-ops are logged but not pushed to Telegram.
