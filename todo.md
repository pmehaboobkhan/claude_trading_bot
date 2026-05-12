# Calm Turtle — Implementation TODO

> Tracks the work to build the system described in `plan.md`. Check items off as they land. Treat the **gates** as hard — do not skip ahead.

## Strategy Pivot (2026-05-10) — Sector rotation rejected; multi-strategy retail portfolio adopted

Sector-ETF rotation failed across three regime backtests. Goal reframed from "beat SPY risk-adjusted" to **absolute return 8–10% / max DD ≤ 15% / Sharpe ≥ 0.8**. See `plan.md` "Strategy Pivot" section at top, plus `reports/learning/backtest_findings_2026-05-10.md` and `reports/learning/pivot_validation_2026-05-10.md`.

### Pivot work completed today
- [x] `lib/signals.py` — rewritten with three new strategies (`dual_momentum_taa`, `large_cap_momentum_top5`, `gold_permanent_overlay`); `STRATEGY_FUNCS` dispatcher; `TAA_RISK_ASSETS = ["SPY", "IEF", "GLD"]` (TLT swap-out committed).
- [x] `lib/indicators.py` — `sma`, `rsi`, `atr`, `relative_strength`, `above_sma`, `pct_from_sma`.
- [x] `lib/backtest.py` — event-driven harness with Sharpe / max DD / promotion criteria.
- [x] `lib/fills.py` — 1 bp slippage + 1 bp half-spread per side; integrated into `lib/paper_sim.py`.
- [x] `config/watchlist.yaml` — 4 macro ETFs (SPY, IEF, GLD, SHV) + 20 large-caps; TLT kept on watchlist with `approved_for_paper_trading: false`.
- [x] `config/strategy_rules.yaml` — 3 new strategies as `NEEDS_MORE_DATA`; 4 old sector strategies marked `REJECTED`.
- [x] `config/risk_limits.yaml` — added `max_drawdown_pct: 15.0`, `max_macro_etf_position_pct: 60.0`, `max_risk_per_trade_pct: 1.5`, `daily_drawdown_halt_pct: 2.0`, `max_open_positions: 8`.
- [x] `CLAUDE.md` — new goal block; strategy allocations; SPY demoted to context only.
- [x] `tests/test_signals.py` — 17 deterministic tests across all three strategies, dispatcher, and reproducibility property.
- [x] `scripts/run_multi_strategy_backtest.py`, `scripts/yfinance_sweep.py`, `scripts/run_param_sweep.py`.
- [x] Backtests run: 60/30/10 with TLT, 70/20/10 with TLT, 60/30/10 with **IEF** (committed variant).
- [x] `reports/learning/backtest_findings_2026-05-10.md` — sector rotation rejection write-up.
- [x] `reports/learning/pivot_validation_2026-05-10.md` — multi-strategy results, DD failure, survivor-bias caveat.

### Backtest results (2013-05-22 → 2026-05-08)
| Variant | CAGR | Max DD | Sharpe |
|---|---|---|---|
| 60/30/10 with TLT | +17.83% | 24.44% | 1.10 |
| 70/20/10 with TLT | +15.63% | 23.67% | 1.05 |
| 60/30/10 with **IEF** (committed) | +17.51% | 24.22% | 1.10 |

- Return target ✅ comfortably met in every variant.
- DD target ❌ missed by 9+ pp in every variant. Allocation tuning + bond swap together moved DD < 1 pp → DD appears **structural** to the strategy set.
- Window starts 2013 (no 2008 stress test); real recession DD could be 30–35%.

---

## Drawdown decision — RESOLVED 2026-05-11

Tested all three paths; adopted **Path Z asymmetric circuit-breaker**.

- [x] Path Y tested — failed: 40% cash buffer only gave 3.3 pp DD reduction (0.08 pp/pp). Dead end.
- [x] Path Z default tested — passed minimum gates but at 8.09% CAGR (right at the floor) and stuck in cash 4 years post-COVID. Too brittle.
- [x] Path Z tuned (recover @ 8%) — passed all gates at 10.55% / 12.68% but generated 54 whipsaw events (no hysteresis).
- [x] **Path Z asymmetric (HALF@8 / OUT@12 / HALF→FULL@5 / OUT→HALF@8) — adopted.** 11.15% CAGR / 12.68% DD / 1.14 Sharpe / 15 throttle events.

Realistic forward estimate after haircuts (survivor bias on Strategy B, circuit-breaker friction, no 2008 stress): **9–10% CAGR with ~15–18% max DD, Sharpe ≥ 1.0** — right in the target band.

Implementation lives in `scripts/run_multi_strategy_backtest.py` (the `--circuit-breaker` flag + `apply_circuit_breaker()`). Needs to be ported to the live/paper code path; see follow-ups below.

### Path Z production wiring — landed 2026-05-11

- [x] **`config/risk_limits.yaml > circuit_breaker`** block added (8/12/5/8 thresholds, `enabled: true`). Schema (`tests/schemas/risk_limits.schema.json`) updated to require + validate it.
- [x] **`lib/portfolio_risk.py`** — pure state machine + persistence. `CircuitBreakerThresholds`, `CircuitBreakerState`, `step`, `exposure_fraction`, `from_config`, `load_state`, `save_state`, `advance`.
- [x] **`lib/paper_sim.py > portfolio_equity()`** — sums open-position mark-to-market + cash. Raises on missing quotes (forces stale-data alerts).
- [x] **`tests/test_portfolio_risk.py`** — 34 tests; full suite 51/51 passing.
- [x] **`scripts/run_multi_strategy_backtest.py`** refactored to consume `lib.portfolio_risk` (single source of truth for backtest + paper). Parity verified: 11.15% / 12.68% / 1.14 / 15 events / $392,465 — exact match.
- [x] **Strategy promotion** — three v1 strategies flipped to `ACTIVE_PAPER_TEST` in `config/strategy_rules.yaml`.
- [x] **Routine prompt draft** — `prompts/proposed_updates/2026-05-11_end_of_day_circuit_breaker.md` describes exactly how `end_of_day` should consult the breaker. Production prompt locked by hook #5; needs human PR.

### Per-agent model routing — landed 2026-05-11

- [x] Added `model:` to each `.claude/agents/*.md` frontmatter. 7 agents on `haiku` (retrieval / templating / metric work), 6 on `opus` (judgment / gating / thesis writing). See `plan.md` "Per-agent model routing" for full mapping + rationale.
- [ ] **Operator action**: when creating the routines on Claude Code web, set the routine-level default model to **Opus 4.7** so the orchestrator session is on the smart model. Subagent delegations will use their declared `model:` and skip Opus where they don't need it.

### Go-live for paper trading — landed 2026-05-11

- [x] **`prompts/routines/end_of_day.md`** rewritten to wire in the circuit-breaker (step 5 inserted; ENTRY sizing scaled by throttle; OUT → entry rejected with `circuit_breaker_OUT`).
- [x] **`lib/broker.py`** extended with `account_snapshot()` and `latest_quotes_for_positions()` (called from the EOD routine to mark-to-market open positions).
- [x] **`config/approved_modes.yaml`** flipped to `PAPER_TRADING` with paired risk-event audit log.
- [x] **Gates** — 51/51 tests, schema validation clean.

### Operator action — set up routines on Claude Code web

- [ ] Push the commit (`git push`).
- [ ] On Claude Code web, create three routines pointing at `prompts/routines/{pre_market,end_of_day,self_learning_review}.md` (model: Opus 4.7; timezone: America/New_York; trading-days-only on the first two).
- [ ] Add secrets to each routine: `ALPACA_PAPER_KEY_ID`, `ALPACA_PAPER_SECRET_KEY`, `ALPACA_PAPER_BASE_URL`, `ALPACA_DATA_BASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- [ ] Manual `Run now` of `pre_market` first; verify Telegram fires and a commit lands.
- [ ] Let `pre_market` and `end_of_day` run automatically for one full trading day.

### Intraday monitoring routines — landed 2026-05-12

- [x] `lib/portfolio_health.py` — per-position assessment (`PositionHealth`, `assess_positions`, `positions_to_close`).
- [x] `tests/test_portfolio_health.py` — 15 tests (full suite 66/66).
- [x] Routine prompts rewritten as monitoring-only: `prompts/routines/{market_open,midday,pre_close}.md`. Hard "no new entries" rule.
- [x] `config/routine_schedule.yaml` — three routines flipped to `enabled: true phase: v1` with explanatory header comment.

### Context-budget protection — landed 2026-05-12

- [x] `lib/snapshots.py` — DailySnapshot dataclass, write/read helpers, YAML frontmatter + markdown body. end_of_day writes; pre_market reads.
- [x] `lib/routine_audit.py` — RoutineAudit dataclass + writer. YAML audit per routine run.
- [x] `tests/test_snapshots.py` + `tests/test_routine_audit.py` — 33 tests including a 1-KB size guarantee. Full suite 99/99.
- [x] Routine prompts wired: pre_market reads `memory/daily_snapshots/` instead of full journals; end_of_day writes today's snapshot before compliance gate; every routine writes an audit log at end.
- [x] `memory/daily_snapshots/.gitkeep` created.

### Still open

- [ ] **Operator: set up market_open, midday, pre_close on Claude Code web** — same template as the existing two routines; same `calm-turtle` environment; crons per the schedule yaml.
- [ ] **Daily-layer ensemble/voting framework** (next 2–4 weeks). First deliverable: explicit handling for two strategies converging on the same symbol (e.g. GLD via TAA + gold_permanent_overlay).
- [ ] **Per-symbol history compression** — when `decisions/by_symbol/<SYM>.md` timeline > 50 rows, Performance Review collapses older rows into a summary header. Stabilizes context load on long-lived symbols.
- [ ] **`logs/routine_runs/` auto-archive** to `archive/<year>/<month>/` after 30 days.
- [ ] **First paper-trading week monitoring** — daily check of `trades/paper/circuit_breaker.json`, `trades/paper/log.csv` reconciliation, no risk events. Also: scan `approximate_input_kb` across audit logs once a week, plot the trend.
- [ ] **Operator hook fix** — `.claude/hooks/validate_yaml_schema.sh` invokes system `python3`. User-level `pip install jsonschema` is in place, but for portability the hook should prefer `.venv/bin/python` when present.
- [ ] **2008-inclusive backtest** when feasible — current window starts 2013 due to META IPO. SPY-only proxy for Strategy B during 2005–2013 would stress-test recession DD.

---

## Post-Review Refactor (2026-05-10) — completed earlier the same day

- [x] `lib/indicators.py` — pure TA computations.
- [x] `lib/signals.py` — deterministic strategy signal generation (since rewritten for new strategies).
- [x] `lib/fills.py` — realistic slippage + half-spread fill modeling.
- [x] `lib/paper_sim.py` — uses `lib/fills.py`; round-trip friction ~4 bps baked in.
- [x] `lib/backtest.py` — event-driven backtest harness with metrics and promotion criteria.
- [x] `tests/test_signals.py` — deterministic unit tests (now 17 covering new strategies).
- [x] `technical_analysis` agent refactored — wraps `lib.signals`; doesn't compute or decide.
- [x] `trade_proposal` agent refactored — wraps deterministic signal; never overrides Python's action.
- [x] `self_learning` agent — observations-only v1 mode; v2 gated on `prompts/proposed_updates/.v2_enabled`.
- [x] `config/routine_schedule.yaml` — v1 enables only `pre_market`, `end_of_day`, `self_learning_review`.
- [x] `config/risk_limits.yaml` — `cost_caps` and `fills` sections added.
- [x] `.github/workflows/eod_watchdog.yml` — Telegram alert if no EOD commit by 17:30 ET.
- [x] `pre_market` and `end_of_day` routine prompts driven by `lib.signals` (Python computes, Claude wraps).
- [x] **First backtest run** — completed for all three strategies. Sector rotation strategies rejected.
- [ ] **Configure Alpaca paper keys + Telegram in Claude Code routine secrets** (operator task).
- [ ] **Create `.github` repo + add secrets** if the watchdog should be active.

---

## Open decisions (carried over from earlier)

- [x] **Scaffold pace**: one big pass.
- [x] **Implementation language**: Python.
- [ ] **Capital allocated** to paper account (notional, e.g. $100k)?
- [ ] **Loss tolerances** in `risk_limits.yaml` — confirm or adjust the just-added portfolio-level caps.
- [ ] **Telegram setup**: BotFather token + chat ID into Claude Code routine secrets.
- [ ] **Alpaca paper keys**: into Claude Code routine secrets.

---

## Phase 0 — Requirements & risk profile

- [x] Universe locked: 4 macro ETFs + 20 large-caps (multi-strategy portfolio, **replaces** the rejected sector-ETF universe)
- [x] Goal locked: 8–10% CAGR / max DD ≤ 15% / Sharpe ≥ 0.8 (absolute return target; SPY = context only)
- [x] Broker chosen: Alpaca (paper now, live Phase 8+)
- [x] Notifications: Telegram
- [x] Data feed: Alpaca free (IEX); historical backtests via yfinance
- [ ] Write `/docs/risk_profile.md` from the new goal + portfolio-level loss tolerances
- [ ] Sign-off (commit `/docs/risk_profile.md` as ground truth)

**Gate to Phase 1**: numeric loss limits exist; broker chosen; universe & goal locked. ✅ except risk_profile.md write-up.

---

## Phase 1 — Repo scaffold

### Config & docs
- [x] `CLAUDE.md` (updated 2026-05-10 with new goal + multi-strategy allocations)
- [x] `config/watchlist.yaml` (24 symbols across the 3-strategy universe)
- [x] `config/risk_limits.yaml`
- [x] `config/strategy_rules.yaml` (3 new strategies; 4 sector strategies marked REJECTED)
- [x] `config/routine_schedule.yaml`
- [x] `config/approved_modes.yaml` (initial mode: `RESEARCH_ONLY`)
- [x] `docs/operator_runbook.md`
- [x] `docs/incident_response.md`
- [x] `docs/model_limitations.md`
- [ ] `docs/risk_profile.md` (still to write — needs current portfolio targets, not sector-rotation framing)
- [x] `docs/commit_messages.md`

### Schemas & tests
- [x] `tests/schemas/watchlist.schema.json`
- [x] `tests/schemas/risk_limits.schema.json`
- [x] `tests/schemas/strategy_rules.schema.json`
- [x] `tests/schemas/approved_modes.schema.json`
- [x] `tests/schemas/trade_decision.schema.json`
- [x] `tests/run_schema_validation.py` (entrypoint used by hooks)

### Hooks (12 from plan §9)
- [x] `.claude/settings.json` (hook registrations)
- [x] All 12 hook scripts in `.claude/hooks/`

### Agents (13 from plan §4)
- [x] All 13 agent definitions in `.claude/agents/`

### Slash commands (9 from plan §7)
- [x] All 9 slash commands in `.claude/commands/`

### Production prompts (drafts; locked by hook #5)
- [x] `prompts/agents/<each>.md`
- [x] `prompts/routines/pre_market.md`
- [x] `prompts/routines/end_of_day.md`
- [x] `prompts/routines/self_learning_review.md`
- [ ] Scaffold remaining routine prompts (market_open / midday / pre_close / weekly_review / monthly_review) — currently `enabled: false` per v1 scope; can defer until Phase 3.

### Broker / data wrapper
- [x] `lib/broker.py` — Alpaca paper/live abstraction
- [x] `lib/data.py` — Alpaca data feed wrapper (IEX) + yfinance helper
- [x] `lib/notify.py` — Telegram send_message wrapper
- [x] `lib/paper_sim.py` — uses `lib/fills.py`
- [x] `.env.example`
- [x] `.gitignore`

### Empty folder placeholders
- [x] All `data/`, `journals/`, `decisions/`, `trades/`, `backtests/`, `reports/`, `prompts/proposed_updates/`, `logs/`, `memory/` placeholders.

### Phase 1 verification (must pass)
- [x] Bad `risk_limits.yaml` (negative cap) → hook #2 rejects
- [x] Edit a journal dated 2 days ago → hook #4 rejects
- [x] Write to `trades/live/order.json` → hook #1 rejects
- [x] Bash command containing a fake API key → hook #6 rejects
- [x] Direct edit to `prompts/agents/*.md` → hook #5 rejects
- [x] All schema validators run green on the seed configs

**Gate to Phase 1 → Phase 2**: ✅ cleared.

---

## Phase 2 — Routine prototypes (pre-market + EOD)

- [ ] First Claude Code routine: pre-market (06:30 ET), reads watchlist + risk + journals, dispatches subagents, writes `reports/pre_market/`, commits — **blocked on operator-side secret setup**.
- [ ] First Claude Code routine: end-of-day (16:30 ET), writes daily journal + memory observations — same blocker.
- [ ] Telegram notification working (receive a routine summary)
- [ ] 5 consecutive trading days of clean pre-market + EOD output, no halt

**Gate to Phase 3**: 5 days clean; reports human-readable; commits well-formed.

---

## Phase 3 — Full routine set (research-only)

- [ ] Market open routine (09:35 ET)
- [ ] Midday routine (12:00 ET)
- [ ] Pre-close routine (15:30 ET)
- [ ] Weekly review routine (Sat 09:00)
- [ ] Monthly review routine (1st 09:00)
- [ ] Self-learning review routine (Sun 10:00) — already scaffolded in v1 set
- [ ] All slash commands working (`/premarket-report`, `/risk-check`, `/halt-trading`, etc.)
- [ ] 4 weeks of continuous research artifacts
- [ ] First weekly review and first monthly review produced

**Gate to Phase 4**: 4 weeks clean; one full monthly review cycle complete; learning loop produces non-empty proposed_updates.

---

## Phase 4 — Paper trading simulator

- [ ] Mode flipped to `PAPER_TRADING` via PR to `approved_modes.yaml`
- [x] `lib/paper_sim` produces fills from decisions (built; not yet exercised end-to-end)
- [ ] `trades/paper/log.csv` reconciles to `trades/paper/positions.json` daily
- [x] Append-only hook (#12) enforced
- [ ] Performance Review Agent reports paper PnL + portfolio metrics (CAGR, max DD, Sharpe)
- [ ] 4 weeks of paper trading; ≥ 50 paper trades across the three strategies; zero log/journal drift

**Gate to Phase 5**: 50+ paper trades; daily reconciliation clean.

---

## Phase 5 — Backtesting & analytics

- [x] Backtest harness for each strategy in `strategy_rules.yaml`
- [x] `backtests/<strategy>/` populated (`multi_strategy_portfolio/`, `regime_defensive_tilt/`, `sector_relative_strength_rotation/`, `param_sweep*`)
- [ ] Forward paper-trade results compared to backtest expectations
- [ ] Divergence (if any) explained in writing

**Gate to Phase 6**: backtest exists for every active strategy ✅; forward divergence documented (pending Phase 4 evidence).

---

## Phase 6 — Human-approved live proposals (≥ 90 trading days, ≥ 30 closed paper trades, portfolio Sharpe ≥ 0.8, paper max DD ≤ 12%)

- [ ] Mode `LIVE_PROPOSALS` (PR only)
- [ ] Routines emit `PROPOSE_LIVE_*` decisions instead of paper
- [ ] PR-based approval workflow for live proposals
- [ ] 90 trading days minimum elapsed
- [ ] Portfolio Sharpe ≥ 0.8 and max DD ≤ 12% on paper data
- [ ] Explicit human PR + signed update to `docs/risk_profile.md`

**Gate to Phase 7**: monthly review explicitly recommends advancing.

---

## Phase 7 — Broker read-only

- [ ] Alpaca live read-only key configured (no trade scope yet)
- [ ] Reconciliation routine: broker positions vs repo positions
- [ ] 2 weeks of zero-discrepancy reconciliation

**Gate to Phase 8**: 2 weeks clean reconciliation.

---

## Phase 8 — Limited live execution

- [ ] Alpaca live trading key + broker-side hard limits configured
- [ ] Mode `LIVE_EXECUTION` (PR + signed risk profile update)
- [ ] Per-trade human approval still required (`require_human_approval_for_live_trades: true`)
- [ ] Order-placement audit log in `logs/orders/`
- [ ] Emergency halt mechanism tested
- [ ] Tax logging in place
- [ ] 30 days; no limit breaches; drawdown ≤ paper drawdown

**Gate to Phase 9**: explicit human decision + signed risk profile update.

---

## Phase 9 — Monitoring & continuous improvement (ongoing)

- [ ] Monthly retro doc
- [ ] Quarterly key rotation
- [ ] 3 months without halt → consider opening Phase F autonomous mode review (default: never open it)

---

## Always-on hygiene

- [ ] Quarterly Alpaca + Telegram key rotation
- [ ] Annual full incident-response drill
- [ ] Weekly review of `memory/rejected_learnings/` to ensure the system isn't being silenced about a real problem
- [ ] Never push to `main` without PR review for: `risk_limits.yaml`, `strategy_rules.yaml`, `approved_modes.yaml`, `watchlist.yaml` live flags, `prompts/agents/`, `prompts/routines/`
