# Calm Turtle — Implementation TODO

> Tracks the work to build the system described in `plan.md`. Check items off as they land. Treat the **gates** as hard — do not skip ahead.

---

## Open decisions (block scaffold)

- [ ] **Scaffold pace**: one big pass, or chunked into reviewable groups?
- [ ] **Implementation language**: Python (recommended) or TypeScript?
- [ ] **Capital allocated** to paper account (notional, e.g. $100k)?
- [ ] **Loss tolerances confirmed**: daily / weekly / monthly limits per `risk_limits.yaml` (current draft: $500 / 2% / 5%) — keep, tighten, or loosen?
- [ ] **Telegram setup**: BotFather token + chat ID gathered (don't paste here; goes into Claude Code routine secrets when we wire notifications)
- [ ] **Alpaca paper keys**: generated at `app.alpaca.markets` (don't paste here; same delivery path as Telegram)

---

## Phase 0 — Requirements & risk profile

- [x] Universe locked: 12 sector ETFs (SPY + 11 SPDRs)
- [x] Goal locked: risk-adjusted vs SPY, drawdown ≤ SPY's
- [x] Broker chosen: Alpaca (paper now, live Phase 8+)
- [x] Notifications: Telegram
- [x] Data feed: Alpaca free (IEX)
- [ ] Write `/docs/risk_profile.md` from above + your final loss-tolerance numbers
- [ ] Sign-off (you commit `/docs/risk_profile.md` as ground truth)

**Gate to Phase 1**: numeric loss limits exist; broker chosen; universe & benchmarks locked.

---

## Phase 1 — Repo scaffold

### Config & docs
- [ ] `CLAUDE.md` (operating manual per plan §8)
- [ ] `config/watchlist.yaml` (12 ETFs per plan §6A)
- [ ] `config/risk_limits.yaml` (per plan §6B)
- [ ] `config/strategy_rules.yaml` (sector-rotation strategies per plan §6C)
- [ ] `config/routine_schedule.yaml`
- [ ] `config/approved_modes.yaml` (initial mode: `RESEARCH_ONLY`)
- [ ] `docs/operator_runbook.md`
- [ ] `docs/incident_response.md`
- [ ] `docs/model_limitations.md`
- [ ] `docs/risk_profile.md`
- [ ] `docs/commit_messages.md`

### Schemas & tests
- [ ] `tests/schemas/watchlist.schema.json`
- [ ] `tests/schemas/risk_limits.schema.json`
- [ ] `tests/schemas/strategy_rules.schema.json`
- [ ] `tests/schemas/approved_modes.schema.json`
- [ ] `tests/schemas/trade_decision.schema.json`
- [ ] `tests/run_schema_validation.{py|ts}` (entrypoint used by hooks)

### Hooks (12 from plan §9)
- [ ] `.claude/settings.json` (hook registrations)
- [ ] `.claude/hooks/block_live.sh`
- [ ] `.claude/hooks/validate_yaml_schema.sh`
- [ ] `.claude/hooks/validate_decision_schema.sh`
- [ ] `.claude/hooks/journal_immutability.sh`
- [ ] `.claude/hooks/block_prompt_overwrites.sh`
- [ ] `.claude/hooks/scan_secrets.sh`
- [ ] `.claude/hooks/block_broker_calls.sh`
- [ ] `.claude/hooks/require_strategy_tests.sh`
- [ ] `.claude/hooks/log_session_start.sh`
- [ ] `.claude/hooks/log_session_end.sh`
- [ ] `.claude/hooks/halt_audit.sh`
- [ ] `.claude/hooks/append_only.sh`

### Agents (13 from plan §4)
- [ ] `.claude/agents/orchestrator.md`
- [ ] `.claude/agents/market_data.md`
- [ ] `.claude/agents/news_sentiment.md`
- [ ] `.claude/agents/technical_analysis.md`
- [ ] `.claude/agents/fundamental_context.md` (sector-aggregate flavor)
- [ ] `.claude/agents/macro_sector.md`
- [ ] `.claude/agents/risk_manager.md`
- [ ] `.claude/agents/portfolio_manager.md`
- [ ] `.claude/agents/trade_proposal.md`
- [ ] `.claude/agents/journal.md`
- [ ] `.claude/agents/compliance_safety.md`
- [ ] `.claude/agents/performance_review.md`
- [ ] `.claude/agents/self_learning.md`

### Slash commands (9 from plan §7)
- [ ] `.claude/commands/premarket-report.md`
- [ ] `.claude/commands/analyze-symbol.md`
- [ ] `.claude/commands/risk-check.md`
- [ ] `.claude/commands/propose-paper-trade.md`
- [ ] `.claude/commands/update-daily-journal.md`
- [ ] `.claude/commands/weekly-review.md`
- [ ] `.claude/commands/monthly-review.md`
- [ ] `.claude/commands/explain-decision.md`
- [ ] `.claude/commands/halt-trading.md`

### Production prompts (drafts; locked by hook #5)
- [ ] `prompts/agents/<each>.md` — production agent prompts (one per subagent)
- [ ] `prompts/routines/pre_market.md`
- [ ] `prompts/routines/market_open.md`
- [ ] `prompts/routines/midday.md`
- [ ] `prompts/routines/pre_close.md`
- [ ] `prompts/routines/end_of_day.md`
- [ ] `prompts/routines/weekly_review.md`
- [ ] `prompts/routines/monthly_review.md`
- [ ] `prompts/routines/self_learning_review.md`

### Broker / data wrapper
- [ ] `lib/broker.{py|ts}` — Alpaca paper/live abstraction; reads env; redacts on log; refuses live until mode allows
- [ ] `lib/data.{py|ts}` — Alpaca data feed wrapper (IEX); freshness stamps
- [ ] `lib/notify.{py|ts}` — Telegram send_message wrapper
- [ ] `lib/paper_sim.{py|ts}` — internal paper-trade simulator (used until Phase 5 broker sandbox)
- [ ] `.env.example` (names only)
- [ ] `.gitignore` (covers `.env*`, `settings.local.json`, `*.pem`, `*.key`)

### Empty folder placeholders
- [ ] `data/market/.gitkeep`
- [ ] `data/news/.gitkeep`
- [ ] `data/fundamentals/.gitkeep`
- [ ] `journals/daily/.gitkeep`
- [ ] `journals/weekly/.gitkeep`
- [ ] `journals/monthly/.gitkeep`
- [ ] `decisions/.gitkeep`
- [ ] `decisions/by_symbol/.gitkeep` (per-symbol decision history files materialize on first decision)
- [ ] `trades/paper/.gitkeep`
- [ ] `trades/live/.gitkeep` (file gated by hook #1)
- [ ] `backtests/.gitkeep`
- [ ] `reports/pre_market/.gitkeep`
- [ ] `reports/end_of_day/.gitkeep`
- [ ] `reports/learning/.gitkeep`
- [ ] `prompts/proposed_updates/.gitkeep`
- [ ] `logs/routine_runs/.gitkeep`
- [ ] `logs/risk_events/.gitkeep`
- [ ] `memory/market_regimes/.gitkeep`
- [ ] `memory/symbol_profiles/.gitkeep`
- [ ] `memory/signal_quality/.gitkeep`
- [ ] `memory/strategy_lessons/.gitkeep`
- [ ] `memory/prediction_reviews/.gitkeep`
- [ ] `memory/risk_lessons/.gitkeep`
- [ ] `memory/model_assumptions/.gitkeep`
- [ ] `memory/agent_performance/.gitkeep`
- [ ] `memory/approved_learnings/.gitkeep`
- [ ] `memory/rejected_learnings/.gitkeep`

### Phase 1 verification (must pass)
- [ ] Bad `risk_limits.yaml` (negative cap) → hook #2 rejects
- [ ] Edit a journal dated 2 days ago → hook #4 rejects
- [ ] Write to `trades/live/order.json` → hook #1 rejects
- [ ] Bash command containing a fake API key → hook #6 rejects
- [ ] Direct edit to `prompts/agents/*.md` → hook #5 rejects
- [ ] All schema validators run green on the seed configs

**Gate to Phase 2**: synthetic bad-PR checklist all rejected by hooks; schema validators clean.

---

## Phase 2 — Routine prototypes (pre-market + EOD)

- [ ] First Claude Code routine: pre-market (06:30 ET), reads watchlist + risk + journals, dispatches Market Data / News / Macro / Technical agents, writes `reports/pre_market/`, commits
- [ ] First Claude Code routine: end-of-day (16:30 ET), writes daily journal + memory observations
- [ ] Telegram notification working (Phase 2 acceptance test: receive a routine summary)
- [ ] 5 consecutive trading days of clean pre-market + EOD output, no halt

**Gate to Phase 3**: 5 days clean; reports human-readable; commits well-formed.

---

## Phase 3 — Full routine set (research-only)

- [ ] Market open routine (09:35 ET)
- [ ] Midday routine (12:00 ET)
- [ ] Pre-close routine (15:30 ET)
- [ ] Weekly review routine (Sat 09:00)
- [ ] Monthly review routine (1st 09:00)
- [ ] Self-learning review routine (Sun 10:00)
- [ ] All slash commands working (`/premarket-report`, `/risk-check`, `/halt-trading`, etc.)
- [ ] 4 weeks of continuous research artifacts
- [ ] First weekly review and first monthly review produced

**Gate to Phase 4**: 4 weeks clean; one full monthly review cycle complete; learning loop produces non-empty proposed_updates.

---

## Phase 4 — Paper trading simulator

- [ ] Mode flipped to `PAPER_TRADING` via `/halt-trading` reverse path (PR-only edit to `approved_modes.yaml`)
- [ ] `lib/paper_sim` produces fills from decisions
- [ ] `trades/paper/log.csv` reconciles to `trades/paper/positions.json` daily
- [ ] Append-only hook (#12) enforced
- [ ] Performance Review Agent reports paper PnL + benchmarks (SPY, equal-weight sector)
- [ ] 4 weeks of paper trading; ≥ 50 paper trades; zero log/journal drift

**Gate to Phase 5**: 50+ paper trades; daily reconciliation clean.

---

## Phase 5 — Backtesting & analytics

- [ ] Backtest harness for each strategy in `strategy_rules.yaml`
- [ ] `backtests/<strategy>/` populated with results
- [ ] Forward paper-trade results compared to backtest expectations
- [ ] Divergence (if any) explained in writing

**Gate to Phase 6**: backtest exists for every active strategy; forward divergence documented.

---

## Phase 6 — Human-approved live proposals (≥ 60 trading days, ≥ 50 trades)

- [ ] Mode `LIVE_PROPOSALS` (PR only)
- [ ] Routines emit `PROPOSE_LIVE_*` decisions instead of paper
- [ ] PR-based approval workflow for live proposals
- [ ] 60 trading days minimum elapsed
- [ ] Sharpe and drawdown hit targets vs both benchmarks (SPY + sector EW)

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
