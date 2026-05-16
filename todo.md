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

- [x] Push the commit (`git push`) — pushed; pre_market and end_of_day commits visible upstream from 2026-05-13.
- [x] On Claude Code web, create three routines pointing at `prompts/routines/{pre_market,end_of_day,self_learning_review}.md` — running; observed in commit log.
- [x] Add secrets to each routine (`ALPACA_*`, `TELEGRAM_*`) — done; routines authenticate to both services.
- [x] Manual `Run now` of `pre_market` first — confirmed by 2026-05-12+ commits with attachments.
- [x] Let `pre_market` and `end_of_day` run automatically for one full trading day — multi-day automatic run since 2026-05-13.

### Intraday monitoring routines — landed 2026-05-12

- [x] `lib/portfolio_health.py` — per-position assessment (`PositionHealth`, `assess_positions`, `positions_to_close`).
- [x] `tests/test_portfolio_health.py` — 15 tests (full suite 66/66).
- [x] Routine prompts rewritten as monitoring-only: `prompts/routines/{market_open,midday,pre_close}.md`. Hard "no new entries" rule.
- [x] `config/routine_schedule.yaml` — three routines flipped to `enabled: true phase: v1` with explanatory header comment.

### Telegram attachments instead of GitHub links — landed 2026-05-12

- [x] `lib/notify.py > send_document` + `send_documents` — `sendDocument` API wrappers with 5 MB cap and mime detection. Never raises; failures logged.
- [x] `tests/test_notify.py` — 15 tests, all mocked. Suite 114/114.
- [x] All 8 routine prompts: notification block drops `/blob/main/<path>` URL bullets; adds `*Artifacts attached below:* <N> files` line + a Step B that calls `send_documents` with the day's report/journal/snapshot.

Cause of the 404s: private repo returns 404 to unauthenticated viewers; even on a public repo, the auto-merge action takes ~30s and fast clicks race it. Attachments sidestep both.

### Telegram bullet format + context line — landed 2026-05-12

- [x] All 8 routine prompts: notification composition section rewritten with bulleted format, bold labels, mandatory `*Context:*` line populated from the audit's `approximate_input_kb`.
- [x] Per-routine concrete examples (pre_market, end_of_day, market_open, midday, pre_close, self_learning_review, weekly_review, monthly_review).
- [x] `lib/notify.py` already uses `parse_mode: "Markdown"` — no code change needed; bullets and bold render natively.

### Context-budget protection — landed 2026-05-12

- [x] `lib/snapshots.py` — DailySnapshot dataclass, write/read helpers, YAML frontmatter + markdown body. end_of_day writes; pre_market reads.
- [x] `lib/routine_audit.py` — RoutineAudit dataclass + writer. YAML audit per routine run.
- [x] `tests/test_snapshots.py` + `tests/test_routine_audit.py` — 33 tests including a 1-KB size guarantee. Full suite 99/99.
- [x] Routine prompts wired: pre_market reads `memory/daily_snapshots/` instead of full journals; end_of_day writes today's snapshot before compliance gate; every routine writes an audit log at end.
- [x] `memory/daily_snapshots/.gitkeep` created.

### Still open

- [ ] **Operator: set up market_open, midday, pre_close on Claude Code web** — same template as the existing two routines; same `calm-turtle` environment; crons per the schedule yaml.
- [x] **Operator: PR-merge five `prompts/proposed_updates/*.md` drafts — landed 2026-05-14.** Direct edits to main with explicit operator authorization (override of the locked-file PR flow). Drafts moved to `prompts/proposed_updates/landed/`. Applied: `strategy_rules > allocation_pct` (config + schema + consolidator config-aware lookup), `eod_signal_consolidation` (Step 4a + Step 7 rewrite + subsumed-decision artifact), `eod_log_archive` (Step 0 housekeeping), `perf_review_history_compression` (Timeline compression in agent Outputs + Forbidden exception). `eod_circuit_breaker` was already in `end_of_day.md` from the 2026-05-11 go-live.
- [x] **Daily-layer ensemble/voting framework — first deliverable landed 2026-05-14:** `lib/signal_consolidator.py` makes same-symbol multi-strategy convergence (GLD via TAA + gold_permanent_overlay) explicit and deterministic. 11 unit tests. Production EOD prompt change drafted in `prompts/proposed_updates/2026-05-14_eod_signal_consolidation.md` (locked file; needs human PR). Structured `allocation_pct` config-field follow-up drafted in `prompts/proposed_updates/2026-05-14_strategy_rules_allocation_field.md`.
- [x] **Per-symbol history compression — landed 2026-05-14:** `lib/symbol_history.py > compress()` collapses entries beyond 50 rows into a `<!-- COMPRESSED:BEGIN -->...<!-- COMPRESSED:END -->` block. Idempotent. 15 unit tests. Performance Review agent change drafted in `prompts/proposed_updates/2026-05-14_perf_review_history_compression.md` (locked file; needs human PR).
- [x] **`logs/routine_runs/` auto-archive — landed 2026-05-14:** `lib/archive.py` + `scripts/archive_routine_logs.py` move files older than 30 days into `archive/<year>/<month>/`. Filename-date based (mtime-safe across worktrees). 12 unit tests. EOD-routine wiring drafted in `prompts/proposed_updates/2026-05-14_eod_log_archive.md` (locked file; needs human PR).
- [x] **Strategy B allocation review (URGENT-ish) — decided 2026-05-15: keep at 30%.** Re-ran 4 reduced-B variants. Production window equivalent, 2008-inclusive collapses but investigation revealed a **CB blend bug** (now fixed); with corrected blend both windows are insensitive to B allocation. Decision: keep B=30 because there's no upside to changing it (was: "wait for survivor-bias fix"). See `reports/learning/strategy_b_allocation_review_2026-05-15.md`.
- [x] **Alpaca free-tier daily-bar staleness — resolved (3 distinct causes, last one 2026-05-16).** (1) IEX lag → hybrid yfinance-for-daily landed 2026-05-14 (`0463154`). (2) Missing yfinance package in the agent env → self-heal + `bootstrap_env.sh` landed 2026-05-15 PM (PR #14). (3) The 2026-05-15/16 4-session blackout was a *third* cause: the `calm-turtle` agent network egress allowlist did not include the Yahoo hosts (`HTTP Error 403: Host not in allowlist`) — not IEX lag, not a missing package. Operator-resolved 2026-05-16 by adding `query1/query2/fc.yahoo.com`. See "Landed 2026-05-16".
- [ ] **VIX data source (from `plan.md`):** Alpaca free IEX does not provide VIX. Live-trading-gate `vix_high_observed` will permanently fail until a VIX-capable feed is wired (Polygon, Tiingo, or paid Alpaca tier).
- [x] **First paper-trading week monitoring — landed 2026-05-15:** `lib/paper_monitor.py` + `scripts/paper_trading_monitor.py` + 33 tests. Reconciliation, CB-state sanity, risk-event count, `approximate_input_kb` trend (with heaviest-file surfacing on WARN/FAIL). Exit 0/1/2 for OK/WARN/FAIL. Live 2026-05-15 run flags 2 real WARNs (6 risk events in 7 days = recent CB churn + reset, expected; `approximate_input_kb=178` near 190 fail threshold, with the 5 heaviest files surfaced inline).
- [x] **Routine context-budget hygiene — landed 2026-05-15.** New "Context budget" subsection in `prompts/routines/{end_of_day,pre_close,market_open,midday}.md` directs the orchestrator NOT to re-read raw market dumps (`data/market/<date>/*.json`), prior-day journals (use `memory/daily_snapshots/<yesterday>.md` instead), or the full pre-market report when the snapshot has the headline. Draft archived under `prompts/proposed_updates/landed/`. Next EOD's `approximate_input_kb` is expected to drop from 178 → ~120 KB; the paper_trading_monitor's heaviest-files surfacing will confirm.
- [x] **Operator hook fix — landed 2026-05-14:** `.claude/hooks/validate_yaml_schema.sh` now prefers `$(repo_root)/.venv/bin/python` when present, falling back to system `python3` for portability.
- [x] **Full-portfolio 2008 stress test — VERDICT REVISED 2026-05-15.** Initial PASS (11.95% CAGR) was invalidated by the CB blend bug fix later same day; corrected verdict is **FAIL on returns** (3.58% CAGR, 12.49% DD, 0.64 Sharpe). DD ceiling held under 2008 stress; return target did not. The 2013-2026 production window (10.60% corrected vs 10.08% legacy) is essentially unaffected by the fix, so live unlock criteria are not invalidated. See `reports/learning/2008_stress_test_2026-05-15.md`.
- [x] **CB blend bug in `run_multi_strategy_backtest.py` — fixed 2026-05-15.** `apply_circuit_breaker` was deriving daily returns from the un-throttled combined equity curve, giving B's compounded equity a floating dollar weight that inflated CAGR by ~8pp on long windows where B has large tail returns. Now uses target-weight blending by default (represents daily rebalance to alloc-a/b/c); legacy blend preserved via `--legacy-cb-blend` for reproducing pre-fix runs.
- [x] **Survivor-bias-corrected Strategy B backtest — landed 2026-05-15.** `--strategy-b-universe-mode as_of` against the hand-curated 2005-2026 point-in-time S&P 100 table. B's standalone 2008-onward return takes a 44% haircut (5,434% → 3,032%); at portfolio level the corrected CB blend already neutralizes most of the bias (3.58% modern → 3.46% as-of CAGR on the stress window). Strategy B allocation stays at 30%. See `reports/learning/strategy_b_survivor_bias_2026-05-15.md`.

### Landed 2026-05-15 PM — observability fixes ([PR #14](https://github.com/pmehaboobkhan/claude_trading_bot/pull/14))

Triggered by the operator noticing today's scheduled `market_open` ran but emitted no Telegram message (per the explicit "notify only on action" rule). Diagnosis surfaced four genuine bugs across reconcile / data-freshness / news-status / observability. All four landed on `fix/reconcile-bootstrap-heartbeat`. Test suite goes 280 → 318.

- [x] **`lib/paper_sim.py > reconcile()` is RESET-aware.** Pre-reset OPENs (GLD/GOOGL/WMT/XOM from before the 2026-05-15 00:31 UTC `_RESET_` marker) were surfacing as phantom discrepancies on an empty `positions.json`. Reuses `RESET_TOKENS` / `_is_reset_row` from `lib.paper_monitor.parse_trade_log`. 6 new tests in `tests/test_paper_sim_reconcile.py`.
- [x] **`lib/data.py` self-heals missing yfinance** + `scripts/bootstrap_env.sh`. The remote scheduled-agent env lacked `yfinance` despite the requirements.txt pin; silent fallback to Alpaca IEX gave the 7-day daily-bar lag in this morning's pre-market. On `ImportError` the data layer does a one-shot `pip install yfinance` per process and re-imports; failure raises a clear `BrokerError`. Bootstrap script is the proactive setup. 3 new tests cover success / pip-failure / one-shot-only.
- [x] **`scripts/news_probe.py` makes the news connector status probe-driven.** HEAD against SEC EDGAR; writes `data/news/<date>/_status.md` with `REACHABLE`/`UNREACHABLE`. Removes the "default-offline" convention in pre_market — midday on 2026-05-14 had already proven the connector works via WebSearch. 9 new tests in `tests/test_news_probe.py`.
- [x] **`lib/notify.send_heartbeat()` for no-op routine runs.** Short Telegram message: routine + UTC + mode + positions + CB state + equity + exit reason. Bounded to ≤3 messages per trading day across market_open / midday / pre_close. Action runs still use `send_html()`. 4 new tests in `tests/test_notify.py`.
- [x] **`prompts/proposed_updates/2026-05-15_heartbeat_and_news_probe.md`** drafted with exact-insert blocks for `market_open.md`, `midday.md`, `pre_market.md` to wire `send_heartbeat()` + `news_probe.py` into the actual routine flow. **Routine-prompt edits are protected (PR-only)** — needs operator application after merge per the PR #12 pattern.
- [x] **`.github/workflows/auto_merge_claude.yml`** — auto-merge widened from `claude/**` only to `claude/**` + `fix/**` + `feat/**` + `chore/**` + `docs/**`. Write-time hooks still gate protected paths; widening only adds branch surface.

### Still open after 2026-05-15 PM

- [ ] **Operator: apply [PR #14](https://github.com/pmehaboobkhan/claude_trading_bot/pull/14)'s routine-prompt drafts** from `prompts/proposed_updates/2026-05-15_heartbeat_and_news_probe.md` to the live `prompts/routines/{market_open,midday,pre_market}.md`. The proposal includes copy-paste-ready inserts.
- [ ] **Operator: wire `scripts/bootstrap_env.sh` into the scheduled remote agents** so `pip install -r requirements.txt` runs before each routine fires. The yfinance self-heal in `lib/data.py` is a safety net, not the primary path. *(NOTE 2026-05-16: this addresses the missing-package cause only; the 2026-05-15/16 blackout was the agent network allowlist — a separate cause, resolved 2026-05-16. Bootstrap wiring remains good hygiene.)*
- [ ] **Wire `scripts/news_probe.py` into the routines.** Covered by the proposal above; lands when the operator applies the drafts.

### Landed 2026-05-16 — data-feed root cause, repo rename, Option B execution arc

Repo renamed **`claude_trading_bot` → `calm_turtle`**. No local action (GitHub redirects the old remote URL; verified). Operator action: confirm each web routine's repo binding → `pmehaboobkhan/calm_turtle`. New entries use the new URL; old links left as-is (redirected).

- [x] **Data-feed blackout root-caused & operator-resolved.** Not a code bug: the `calm-turtle` Claude Code web agent's network egress allowlist lacked the Yahoo Finance hosts (`HTTP Error 403: Host not in allowlist`, all 25 symbols, last good bar 2026-05-08, NO_TRADE × 4 sessions). Proven by reproducing `lib.data` locally (worked). Distinct from the missing-package self-heal. Operator added `query1/query2/fc.yahoo.com`; empirical host-capture (yfinance 1.3.0 + curl_cffi) shows only `query1/query2` are hit; `finance.yahoo.com` recommended as defensive add. `www.sec.gov`/pip hosts confirmed not needed by any v1 routine.
- [x] **Web-routine instruction fixes** (commit `c93ec7a`, `prompts/web_routines_instructions/` — allowed path, not PR-locked). `monthly_review.md` was a 242-line spec-dump → consistent short wrapper; `self_learning_review.md` gained its missing SAFE_MODE clause. Operator must paste the two changed files into the web-UI Instruction boxes.
- [x] **Option B (Market-On-Close execution) — PRs [#16](https://github.com/pmehaboobkhan/calm_turtle/pull/16)–[#19](https://github.com/pmehaboobkhan/calm_turtle/pull/19) merged. Backtest re-validated; NOT enabled.** #16 MOC primitives (dormant, 9 TDD tests). #17 signal-proxy gate → **FAIL 0.8667** (real, isolated to `large_cap_momentum_top5` which needs the exact close; A/C clean). #18 path (a) next-open re-baseline → portfolio **+10.14% / 12.45% DD / 1.05 Sharpe, PASS**; `lib.backtest` gained `fill_timing` (default `close` bit-identical). #19 as_of robustness (2×2 all PASS) + per-period attribution: modern next_open is sign-stable ≈−0.5pp (real momentum drag); **as_of "+0.88pp" is period-selection NOISE (sign flips across halves)**. Carry-forward assumption: budget B at **≈−0.5pp realistic-execution drag, no upside**. Memos: `reports/learning/{moc_signal_proxy_validation,strategy_b_next_open_revalidation,strategy_b_asof_next_open_robustness,strategy_b_fill_attribution}_2026-05-16*`.

### Still open after 2026-05-16

- [ ] **Go live on Alpaca paper — Monday 2026-05-18.** Simple model adopted ([PR #20](https://github.com/pmehaboobkhan/calm_turtle/pull/20), Alpaca-authoritative mirror): Alpaca is the source of truth, no phantom fills, no false halt, zero PR-locked edits. Supersedes the MOC + per-strategy proposals. Fills next-open (≈−0.5pp/yr vs backtest — that's the real friction we're going live to observe). **Operator steps only:** merge PR #20; web env → `BROKER_PAPER=alpaca` + Alpaca paper keys + repo binding `pmehaboobkhan/calm_turtle` + keep Yahoo/Alpaca allowlist. Book flat/aligned from the 2026-05-15 reset — no re-reset.
- [ ] **Operator: confirm web-routine repo bindings → `pmehaboobkhan/calm_turtle`** and paste the two corrected web-instruction files into the web UI; add `finance.yahoo.com` to the agent allowlist (defensive).

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
- [x] **Configure Alpaca paper keys + Telegram in Claude Code routine secrets** — done; routines authenticate to both.
- [ ] **Create `.github` repo + add secrets** if the watchdog should be active.

---

## Open decisions (carried over from earlier)

- [x] **Scaffold pace**: one big pass.
- [x] **Implementation language**: Python.
- [x] **Capital allocated** to paper account — $100k notional set in `config/risk_limits.yaml > account.paper_starting_capital`.
- [x] **Loss tolerances** in `risk_limits.yaml` — portfolio-level caps locked: daily 0.5% / weekly 2% / monthly 5% / max DD 15% / per-trade 1.5%.
- [x] **Telegram setup**: BotFather token + chat ID configured in Claude Code routine secrets (routines firing attachments).
- [x] **Alpaca paper keys**: configured in Claude Code routine secrets (routines authenticating).

---

## Phase 0 — Requirements & risk profile

- [x] Universe locked: 4 macro ETFs + 20 large-caps (multi-strategy portfolio, **replaces** the rejected sector-ETF universe)
- [x] Goal locked: 8–10% CAGR / max DD ≤ 15% / Sharpe ≥ 0.8 (absolute return target; SPY = context only)
- [x] Broker chosen: Alpaca (paper now, live Phase 8+)
- [x] Notifications: Telegram
- [x] Data feed: Alpaca free (IEX); historical backtests via yfinance
- [x] Write `/docs/risk_profile.md` from the new goal + portfolio-level loss tolerances — landed 2026-05-14.
- [ ] Sign-off (commit `/docs/risk_profile.md` as ground truth — pending operator signature on the PR that merges the rewrite)

**Gate to Phase 1**: numeric loss limits exist; broker chosen; universe & goal locked. ✅ — risk_profile.md write-up landed 2026-05-14, awaiting operator sign-off.

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
- [x] `docs/risk_profile.md` — rewritten 2026-05-14 for the multi-strategy retail portfolio. Captures 8–10% / 15% DD / Sharpe 0.8 goal, allocations, loss tolerances, halt triggers, live unlock criteria, and known limitations (survivor bias, 2008 stress test pending, VIX data absence). Sign-off slot pending operator signature on PR merge.
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

- [x] First Claude Code routine: pre-market (06:30 ET) — running on Claude Code web; commits visible 2026-05-12 → 2026-05-14.
- [x] First Claude Code routine: end-of-day (16:30 ET) — running; commits visible 2026-05-12 → 2026-05-14.
- [x] Telegram notification working — `lib/notify.py > send_documents` is wired into every routine prompt's notification step; given multi-day uninterrupted routine commits, delivery appears unblocked (operator to confirm explicitly if not already).
- [ ] 5 consecutive trading days of clean pre-market + EOD output, no halt — **3 of 5 done** (per `scripts/check_phase2_gate.py` run 2026-05-15: CLEAN on 2026-05-12, 2026-05-13, 2026-05-14; 2026-05-15 today is INCOMPLETE — EOD pending). Need today + 2026-05-18 (Mon) to land clean for the gate to clear by EOD 2026-05-18.

**Gate to Phase 3**: 5 days clean; reports human-readable; commits well-formed.

**Gate automation:** `lib/phase2_gate.py` + `scripts/check_phase2_gate.py` (landed 2026-05-15). Per-day evaluation against mechanical criteria (pre-market + EOD commit present, no halt entries, journal ≥ 2 KB, audit `exit_reason` clean). 18 unit tests. Run before claiming gate-pass:
```
python3 scripts/check_phase2_gate.py            # rigorous 5-day check
python3 scripts/check_phase2_gate.py --days 10  # wider visibility
```
Exit 0 means gate passes; exit 1 means more clean days needed (or a recent day failed).

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

- [x] Mode flipped to `PAPER_TRADING` via PR to `approved_modes.yaml` (landed 2026-05-11; current `mode: PAPER_TRADING`).
- [x] `lib/paper_sim` produces fills from decisions — exercised end-to-end; EOD commits show actual PnL (e.g. 2026-05-14 PnL +$842.36, 4 open positions).
- [ ] `trades/paper/log.csv` reconciles to `trades/paper/positions.json` daily — manual reconciliation today; first-paper-trading-week monitoring script (above) will automate this.
- [x] Append-only hook (#12) enforced.
- [x] Performance Review Agent reports paper PnL + portfolio metrics — visible in EOD commit messages; CAGR/Sharpe/max-DD pending sample-size threshold (`N >= 30 trades` per agent guardrail).
- [ ] 4 weeks of paper trading; ≥ 50 paper trades across the three strategies; zero log/journal drift — **in progress**. Paper trading started 2026-05-11; far from 4 weeks and 50 trades.

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
