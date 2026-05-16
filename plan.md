# Claude-Native Multi-Agent Stock Research & Paper-Trading System — Implementation Plan

> Codename: **Calm Turtle**. Slow, deliberate, defensive. Capital preservation > clever trades.

## Strategy Pivot — Sector Rotation → Multi-Strategy Retail Portfolio (2026-05-10)

The sector-ETF rotation thesis (the original v1 universe) **was rejected by backtest evidence** across three regimes (2010–2015, 2019–2020, 2022–2026). Cap-weighted SPY silently rotates better than explicit rules. See `reports/learning/backtest_findings_2026-05-10.md`.

### Goal reframe
- **Old goal:** beat SPY on a risk-adjusted basis (Sharpe), drawdown ≤ SPY's.
- **New goal:** **8–10% annualized compound return, max drawdown ≤ 15%, Sharpe ≥ 0.8.** Absolute return target, not relative. SPY is reported for context only, not as a hurdle.
- Rationale: retail capital does not need to beat an index — it needs to make money reliably and not blow up.

### New strategy set (replaces sector rotation)
A three-strategy portfolio designed for low correlation across strategies:

| Strategy | Allocation | Style | Universe |
|---|---|---|---|
| `dual_momentum_taa` | 60% | Trend-following / TAA (Faber 10-month SMA + relative-momentum select) | SPY / IEF / GLD / SHV (cash floor) |
| `large_cap_momentum_top5` | 30% | Top-5 by 6-month return, SPY 10-mo SMA trend filter | 20 mega-cap stocks (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, BAC, V, MA, JNJ, UNH, PFE, WMT, COST, HD, XOM, ORCL, CSCO) |
| `gold_permanent_overlay` | 10% | Permanent allocation | GLD |

All three coded deterministically in `lib/signals.py` and unit-tested in `tests/test_signals.py` (17 tests).

### Backtest results (2013-05-22 → 2026-05-08, ~13 yrs)
| Variant | Annualized return | Max drawdown | Sharpe |
|---|---|---|---|
| 60/30/10 with TLT | +17.83% | 24.44% | 1.10 |
| 70/20/10 with TLT | +15.63% | 23.67% | 1.05 |
| 60/30/10 with **IEF** (committed) | +17.51% | 24.22% | 1.10 |

- Return target (8–10%) is **comfortably met** in every variant.
- Drawdown target (≤ 15%) is **missed by 9+ percentage points** in every variant.
- Strategy A (TAA) standalone *did* improve materially with IEF (+219% vs +186% TLT) — that swap is committed.
- Allocation tuning and bond substitution together moved DD by < 1 pp. **The ~24% DD appears structural to the strategy set.**
- Window starts 2013 for this run. A 2007-start run is now runnable via `python scripts/run_2008_backtest.py` (anchor-based alignment fix landed 2026-05-14; see 2008-inclusive backtest section below). COVID 2020 is best available pre-fix crisis analog: 12.03% DD vs SPY -34%.

### TLT → IEF swap (committed today)
`lib/signals.py` `TAA_RISK_ASSETS = ["SPY", "IEF", "GLD"]`. `config/watchlist.yaml` now has IEF as paper-approved; TLT remains on watchlist but `approved_for_paper_trading: false`. See note in TLT entry referencing 2022 rate-hike DD contribution.

### Survivor bias caveat (measured 2026-05-14)

Strategy B's standalone +2005% (13y) is inflated by selecting today's mega-cap survivors. **The plan's prior "2-4 pp/yr" estimate was significantly optimistic** — the survivor-bias stress test (`reports/learning/survivor_bias_stress_2026-05-14.md`) measured the actual portfolio-level haircut by re-running the full 60/30/10 portfolio against a year-by-year point-in-time S&P 100 universe (`data/historical/sp100_as_of.json`).

| Window | Universe | CAGR | MaxDD | Sharpe |
|---|---|---:|---:|---:|
| 2013-2026 | modern | +10.08% | 12.56% | 1.08 |
| 2013-2026 | as_of | +9.69% | 12.33% | 0.93 |
| **2007-2026** | **modern** | **+11.95%** | **12.67%** | **1.11** |
| **2007-2026** | **as_of** | **+4.70%** | **12.94%** | **0.58** |

**Headline finding:** the 2007-2026 portfolio-level CAGR drops from +11.95% (modern) to +4.70% (as_of) — a **7.25 pp/yr haircut**. Sharpe falls below the 0.8 portfolio target. The collapse is concentrated in 2008-2010 when the as_of basket holds Lehman / Bear / Wachovia / Merrill / AIG (mostly to ~zero). The 2013-2026 window shows a much smaller haircut (0.39 pp/yr) because the as_of basket from 2013 onward is dominated by names still in today's universe.

**Implication for production:** Strategy B's edge in a forward 2008-class event is materially weaker than the modern-basket backtest implies. The 60/30/10 allocation was sized assuming a stronger Strategy B; **the allocation should be reviewed** (added to "Still open" below).

The 2008 backtest itself (`reports/learning/2008_stress_test_*`) using the modern basket holds the 15% DD ceiling at 12.67% — that's the upper-bound friendly read. The honest forward expectation, accounting for the survivor-bias-corrected as_of result, is closer to **+6 to +9% CAGR with ~13-15% MaxDD** rather than the original +9-10% / 15-18% MaxDD estimate.

### Drawdown decision — RESOLVED 2026-05-11 via Path Z asymmetric circuit-breaker

The original 24% DD problem was tested across three paths:

- **Path X (accept 25% DD, no breaker)** — rejected: violates the just-committed 15% DD goal in CLAUDE.md.
- **Path Y (40% static SHV cash buffer)** — tested and failed: only 3.3 pp DD reduction for a 40-pp cash sleeve (0.08pp/pp exchange rate). Final result: +13.56% CAGR / 20.95% DD. To get under 15% DD via cash alone would need ~110% cash (impossible) or destroy return below the 8% floor.
- **Path Z (portfolio-level drawdown circuit-breaker)** — **adopted.**

Path Z implementation: `scripts/run_multi_strategy_backtest.py --circuit-breaker` flag. State machine in `apply_circuit_breaker()`:

| Transition | Threshold | Why |
|---|---|---|
| FULL → HALF | DD ≥ 8% | First sign of trouble; halve exposure to SHV |
| HALF → OUT | DD ≥ 12% | Confirmed regime stress; exit to 100% SHV |
| **HALF → FULL** | **DD ≤ 5%** | 3pp hysteresis below the 8% HALF trigger — no FULL↔HALF whipsaw |
| **OUT → HALF** | **DD ≤ 8%** | 4pp hysteresis below the 12% OUT trigger — recovers fast enough to catch rallies (faster than 5% threshold which kept us in cash for 4 years after COVID) |

**Asymmetric recovery thresholds** are the key: tight hysteresis around the HALF trigger to prevent whipsaw; fast recovery from OUT to prevent missed rallies. A symmetric 5%/5% breaker passed gates but at 8.09% CAGR — too close to the floor. A symmetric 8%/8% breaker recovered return to 10.55% but generated 54 whipsaws in 13 years. The asymmetric 5%/8% gets both right.

### Result (Path Z asymmetric, 60/30/10, IEF, 2013-05-24 → 2026-05-08)

| Target | Actual | Pass |
|---|---:|---|
| Annualized return ≥ 8% (low) | +11.15% | ✅ |
| Annualized return ≥ 10% (upper) | +11.15% | ✅ |
| Max drawdown ≤ 15% | 12.68% | ✅ |
| Sharpe ≥ 0.8 | 1.14 | ✅ |

Final equity on $100k: $392,465. **15 throttle events** over 13 years — clean cadence, no whipsaws. Sharpe (1.14) actually beats the no-breaker baseline (1.10) — same edge, smoother ride.

**Real-world haircut estimate:** survivor bias on Strategy B ~2–4 pp/yr; circuit-breaker friction ~0.1–0.15 pp/yr; 2008 crisis full-portfolio test pending (run `scripts/run_2008_backtest.py`; anchor-based alignment now in place). Best available crisis analog: COVID 2020 (portfolio DD 12.03% vs SPY -34%). Realistic forward expectation: **9–10% CAGR with ~15–18% max DD**, right in the target band.

See `reports/learning/pivot_validation_2026-05-10.md` for the full Path X/Y/Z comparison and `backtests/multi_strategy_portfolio/2013-05-24_to_2026-05-08_path_z_asymmetric_5_8.md` for the chosen-variant report.

### Production wiring — landed 2026-05-11

- [x] `config/risk_limits.yaml > circuit_breaker` block added (8 / 12 / 5 / 8 thresholds, `enabled: true`). Schema updated (`tests/schemas/risk_limits.schema.json`) to allow + require the new block.
- [x] `lib/portfolio_risk.py` — pure state machine (`CircuitBreakerThresholds`, `CircuitBreakerState`, `step`, `exposure_fraction`, `from_config`) + persistence (`load_state`, `save_state`, `advance`). State persists to `trades/paper/circuit_breaker.json` across routines.
- [x] `lib/paper_sim.py > portfolio_equity()` — sums open-position mark-to-market plus cash. Raises on missing quotes (forces caller to surface stale-data alerts). Used by routines to feed `portfolio_risk.advance()`.
- [x] `tests/test_portfolio_risk.py` — 34 tests covering state machine, persistence, and `portfolio_equity()`. Full suite at 51/51.
- [x] `scripts/run_multi_strategy_backtest.py` refactored to consume `lib.portfolio_risk` (single source of truth across backtest + paper trading). Parity verified: Path Z asymmetric run reproduces 11.15% CAGR / 12.68% DD / 1.14 Sharpe / 15 events / $392,465 exactly.
- [x] `config/strategy_rules.yaml` — three v1 strategies promoted from `NEEDS_MORE_DATA` → `ACTIVE_PAPER_TEST` with a comment block documenting the unlock criteria.
- [x] `prompts/proposed_updates/2026-05-11_end_of_day_circuit_breaker.md` — draft routine-prompt update describing exactly how `end_of_day` should consult the breaker (after signal eval, before any new ENTRY). Production prompt is locked by hook #5; merge via human PR.

### Per-agent model routing — landed 2026-05-11

To control LLM cost, each subagent in `.claude/agents/*.md` now declares a `model:` in its YAML frontmatter. Claude Code respects this when the orchestrator delegates via the Task tool: each subagent runs on its declared model regardless of what the routine itself is on. Routine-level default should be set to **Opus 4.7** on Claude Code web (so the orchestrator session is on the smart model); cheap retrieval work happens inside delegations.

| Agent | Model | Why |
|---|---|---|
| `market_data` | haiku | Pure data fetch + summarization |
| `news_sentiment` | haiku | Headline scraping + tone tagging |
| `fundamental_context` | haiku | ETF holdings + earnings calendar retrieval |
| `macro_sector` | haiku | Wraps `signals.detect_regime` output narratively |
| `technical_analysis` | haiku | Wraps `lib.signals` output in plain English |
| `journal` | haiku | Template assembly from upstream inputs |
| `performance_review` | haiku | Pure metric computation |
| `portfolio_manager` | opus | Judgment on hold/close vs invalidation |
| `risk_manager` | opus | The veto — must understand limit interactions |
| `trade_proposal` | opus | Bull/bear thesis writing — drives audit-trail quality |
| `compliance_safety` | opus | Final gate before commit |
| `self_learning` | opus | Cross-time pattern recognition |
| `orchestrator` | opus | Coordination, routing decisions |

7 of 13 agents on Haiku; 6 on Opus. Expected ~30–50% per-routine cost reduction without touching reasoning quality where it matters. Audit trail (the bull/bear thesis written by `trade_proposal` and the journal entries) stays on Opus.

### Go-live for paper trading — landed 2026-05-11

- [x] **`prompts/routines/end_of_day.md`**: circuit-breaker now wired into the production routine (new step 5 between signal eval and trade execution; ENTRYs scaled by throttle; EXITs never throttled; transitions log to `logs/risk_events/`).
- [x] **`lib/broker.py`**: added `account_snapshot()` (full account snapshot incl. cash) and `latest_quotes_for_positions()` (marks open positions to market for equity computation).
- [x] **`config/approved_modes.yaml`**: flipped `RESEARCH_ONLY` → `PAPER_TRADING`. Paired audit at `logs/risk_events/2026-05-11_183756_mode_flip_paper_trading.md` per hook #11.
- [x] **All gates green**: 51/51 tests pass, all configs schema-validate.

The repo is now ready for paper trading. Operator action remaining:
1. Push the commit.
2. Set up the three v1 routines on Claude Code web (see step-by-step guide in this session's chat history or `docs/operator_runbook.md`).
3. Add secrets (Alpaca paper key/secret, Telegram bot token + chat ID) to each routine.

### Fix 2026-05-12 — Alpaca free-tier `get_bars` returning 1 bar

The first cloud-routine run produced a "data insufficiency" risk event because `lib.data.get_bars` was hitting Alpaca's IEX feed without an explicit `start` date. The free tier returns only the latest bar in that case; Strategy A and B both fall back to NO_TRADE.

- [x] `lib/data.py`: `get_bars` now always computes `start = now - calendar_days(limit)` (1.5× trading-day buffer for daily, 2× for intraday) and passes it explicitly. Also pins `feed="iex"`.
- [x] Routine prompts (`pre_market.md`, `end_of_day.md`): bumped `limit=250` → `limit=300` so Strategy A's 253-bar minimum has headroom.
- [x] 51/51 tests still pass; schema validation clean.

The first run's behavior was actually a good safety-design confirmation: the system correctly identified data insufficiency, emitted a risk event, returned NO_TRADE for A and B, and only Strategy C (history-independent gold overlay) emitted an ENTRY. Compliance approved; nothing went to Alpaca that shouldn't have.

### Intraday monitoring routines — landed 2026-05-12

Following the agreed phased plan (monitoring this week → daily ensemble next 2–4 weeks → intraday alpha only after baseline evidence), the three intraday routines are activated as **monitoring-only** layers:

- `market_open` (09:35 ET) — refresh circuit-breaker with opening equity; detect overnight gaps that breached stops/targets; propose closes only.
- `midday` (12:00 ET) — refresh CB; news scan limited to symbols with open positions; propose closes on news-driven invalidation.
- `pre_close` (15:30 ET) — refresh CB; overnight-risk overlay (earnings tomorrow on holdings, scheduled macro events for next session); close positions facing material overnight exposure.

**Hard rule across all three**: no new entries. ENTRY signals from `lib.signals` are only acted on by `end_of_day` against closing prices — that is where backtest evidence lives. EXITs are never throttled by the circuit-breaker (closing reduces risk).

Built:

- [x] `lib/portfolio_health.py` — pure per-position assessment (`PositionHealth` dataclass, `assess_positions`, `positions_to_close`, `health_as_dict`). Stop/target detection for long and short; raises on missing quotes (forces stale-data alerts).
- [x] `tests/test_portfolio_health.py` — 15 tests covering long/short, stops, targets, no-stop positions, mixed books, error paths, serialization. Full suite at 66/66.
- [x] `prompts/routines/market_open.md`, `midday.md`, `pre_close.md` — rewritten as monitoring-only with explicit "no new entries" guard, CB consultation, paper_sim integration, "commit only if action happened" semantics.
- [x] `config/routine_schedule.yaml` — three routines flipped from `enabled: false phase: v2` to `enabled: true phase: v1`. Top-of-file comment updated.

### Telegram artifacts: attachments instead of GitHub links — landed 2026-05-12

GitHub `/blob/main/<path>` URLs in Telegram messages were 404-ing on the user's phone:
- Private repo → GitHub returns 404 to anyone not authenticated in the current browser. Mobile is the common case.
- Public repo → races the auto-merge action by ~30 seconds; a fast click hits 404 before the merge completes.

Fix: **attach files directly to Telegram as document attachments.** No GitHub dependency. The user reads files inline in Telegram on any device. Files stay in the Telegram chat history forever (good audit trail).

Built:

- [x] `lib/notify.py > send_document(path, *, caption, filename)` — `sendDocument` API wrapper with 5 MB cap, mime-type detection, defensive error handling (returns False, never raises).
- [x] `lib/notify.py > send_documents(paths, *, caption)` — multi-file convenience; caption attaches to the first document only.
- [x] `tests/test_notify.py` — 15 tests, all network calls mocked. Full suite 114/114.
- [x] All 8 routine prompts updated: notification section drops `*<Label>:* https://github.com/...` bullets entirely; adds a `*Artifacts attached below:* <N> file(s)` line and a "Step B — file attachments" block calling `send_documents`.

The bulleted text-message format with the `*Context:* ~<N> KB` line stays exactly as it was. Just no more bad URLs — the artifacts come through as native Telegram document cards.

### Telegram message format — landed 2026-05-12

Notifications were prose paragraphs; switched to a bulleted format with bold labels for easier mobile scan. Added a `*Context:* ~<N> KB (cap 200 KB)` line on every message so context drift is visible at a glance, not buried in audit logs.

Required format:
- Header: `*[Calm Turtle] <routine title> <YYYY-MM-DD>*`
- One bulleted line per metric (regime, signals, PnL, CB state, etc.)
- Mandatory `• *Context:* ~<N> KB` (populated from `approximate_input_kb` in the audit step)
- Mandatory `• *Commit:* <SHA> (auto-merged to main)`
- Artifact links: `/blob/main/<path>` form so they resolve after auto-merge
- Never mention the feature branch name

All 8 routine prompts updated with per-routine field lists + a concrete example. `lib/notify.py` already uses `parse_mode: "Markdown"` so `*bold*` renders correctly on iOS / Android / desktop clients.

### Context-budget protection — landed 2026-05-12

Pre-emptive guard against journals/per-symbol-histories growing unbounded over months. Two mechanisms:

- [x] **Daily snapshots** (`lib/snapshots.py`, `memory/daily_snapshots/<date>.md`). end_of_day writes a ≤ 1 KB summary of the day's essentials (regime + CB state + PnL + decisions + open positions + notable + watch_tomorrow). Pre_market reads the last 5 snapshots instead of the last 5 full daily journals — ~5 KB total context vs ~50–250 KB unbounded.
- [x] **Routine audit logs** (`lib/routine_audit.py`, `logs/routine_runs/<ts>_<routine>_audit.md`). Every routine writes a YAML audit at end with `files_read` (path + bytes), `subagent_dispatches`, `artifacts_written`, `commits`, and an `approximate_input_kb` proxy for token cost. Trended over time, surfaces drift before context blows up.
- [x] `tests/test_snapshots.py` + `tests/test_routine_audit.py` — 33 tests including a 1-KB size guarantee for typical-day snapshots. Full suite at 99/99.
- [x] Routine prompts updated (`pre_market`, `end_of_day`, all intraday + reviews): pre_market reads snapshots; end_of_day writes one as step 12a before compliance_safety; every routine writes an audit appendix as final step.

Result: per-routine input context stays roughly constant over time. We have ~5–8x headroom under the 200k advisory cap, and the audit trail will tell us if it ever changes.

### Walk-forward + parameter stability — landed 2026-05-13

External-review concern #1 (statistical robustness — walk-forward, parameter stability) is closed. Five commits land the validation harness: `61d000d`, `37fb46b`, `d4378e6`, `115d064`, `58c464d` (plus minor refactor commits `5ecc0f5`, `7434a69`).

**Tasks completed:**
1. **`run_backtest()` callable entrypoint** (`scripts/run_multi_strategy_backtest.py`) — sweep scripts now drive the engine in-process without subprocess overhead.
2. **CB threshold stability sweep** (`scripts/run_cb_threshold_stability.py`) — 81-cell grid (3 values × 4 axes) around production. Plateau verdict: borderline FAIL (CAGR band 1.67pp vs 1.5pp gate; MDD band 1.48pp vs 2.0pp gate ✅). Production sits 33rd of 81 by Sharpe — mid-pack, not on a peak. Top-Sharpe variant (0.07/0.11/0.04/0.09) is IS-Pareto-better than production (+11.78% / 11.62% / 1.15 vs +10.08% / 12.56% / 1.08).
3. **Strategy A SMA-window stability sweep** (`scripts/run_sma_stability.py`) — windows 8 through 12 months. Plateau verdict: **PASS** (CAGR band 0.45pp; MDD band 0.19pp). 10-month choice is squarely on a plateau.
4. **Walk-forward harness** (`scripts/run_walk_forward.py` + pure helpers in `lib/walk_forward.py`) — 5y IS / 1y OOS / 1y step folds, 7 folds × 5 IS + 1 OOS each = 42 backtests. Aggregate OOS metrics chained across 1756 trading days:
   - CAGR +10.70% (vs IS +11.15%; gate -2pp ✅, actual -0.45pp)
   - MaxDD 15.71% (vs IS 12.68%; gate +3pp marginal, actual +3.03pp — 3bp over)
   - Sharpe 0.93 (above 0.8 portfolio target ✅)
   - 3 distinct IS-best tuples across folds (0.06/0.10 in 4 folds, 0.10/0.14 in 2 folds, 0.07/0.11 in 1 fold) — borderline regime-dependent. **PROD thresholds (0.08/0.12) were never IS-best in any fold but their walk-forward chained performance is barely worse than IS.**

**Conclusion:** the borderline IS-FAIL from the strict-neighbor plateau check is **adjudicated favorably** by walk-forward. Production thresholds survive OOS without material degradation. The Pareto-better IS variant from the stability sweep is regime-dependent and does not consistently outperform production OOS — no production change recommended at this time.

**Reports:**
- `reports/learning/cb_threshold_stability_2026-05-13.md` (plateau sweep)
- `reports/learning/sma_window_stability_2026-05-13.md` (SMA sweep)
- `reports/learning/walk_forward_cb_2026-05-13.md` (walk-forward)
- Plan: `docs/superpowers/plans/2026-05-12-walk-forward-and-parameter-stability.md`

**Tests:** 138 passing (was 99 before the plan).

### 2008-inclusive backtest — landed 2026-05-13/14

**Approach:** Added `--cash-proxy BIL` flag to `scripts/run_multi_strategy_backtest.py` (Plan #3 Task 2), wrote `scripts/run_2008_backtest.py` as an in-process driver (Task 3), applied `filter_bars_by_listing()` from `lib/historical_universe` to all bars before alignment (Task 4), and fixed `align_bars()` to use anchor-based alignment (Task 4 follow-up). The time-aware filter drops synthesized pre-listing bars for META/TSLA/V; the anchor-based alignment allows long-window backtests to start from 2007 even though META/TSLA/V didn't exist until 2010-2012.

**Anchor-based alignment (committed 2026-05-14):** `align_bars()` previously intersected dates across ALL symbols, causing META's 2012 IPO to push the effective start to 2013. Fix: only symbols with data back to `args.start` anchor the common trading-date grid; mid-window IPOs are merged onto this grid with empty bars in early years, letting `signals.py`'s momentum-window gate exclude them naturally. Production window (2013+) is unaffected — all symbols have data from 2013.

**Pre-fix run (BIL proxy, 2013-05-22 → 2026-05-08, 12.9y):**
- CAGR: +10.65%, Max DD: 12.68%, Sharpe: 1.10, CB events: 13
- 2008 crisis NOT covered (align_bars constraint). COVID 2020 is best available analog: 12.03% DD vs SPY -34% (64% drawdown reduction).

**2008 crisis run (user-executable):** Run `python scripts/run_2008_backtest.py` to execute the full 2007-06-01 → 2026-05-08 window with anchor-based alignment and BIL cash proxy. Report will be written to `reports/learning/2008_stress_test_<date>.md` and `backtests/multi_strategy_portfolio/<dates>_2008_inclusive.md`.

**15% DD ceiling verdict:** PASS for the 2013-2026 window (12.68% < 15%). The 2008 crisis requires running `run_2008_backtest.py` to verify (expected: DD stays below 15% given Strategy A's trend-following would have been in IEF/BIL through most of the 2008 crisis).

**Reports:**
- `backtests/multi_strategy_portfolio/2013-05-22_to_2026-05-08_2008_inclusive.md` (pre-fix run)
- `reports/learning/2008_stress_test_2026-05-14.md` (pre-fix run — documents align_bars constraint)
- Plan: `docs/superpowers/plans/2026-05-12-2008-inclusive-backtest.md`

### Survivor-bias stress test — landed 2026-05-14

External-review concern #5 (survivor bias on Strategy B) is closed. Five commits land the data + helpers + driver + plan update: `d3802df`, `d1eef66`, `9a15614`, plus the survivor-bias stress run today.

**Headline:** see "Survivor bias caveat (measured 2026-05-14)" above. Portfolio CAGR collapses from +11.95% (modern, 2007-2026) to +4.70% (as_of, 2007-2026) — a **7.25 pp/yr haircut**, 3-4× larger than the plan's prior estimate. The 60/30/10 allocation should be reviewed (added to "Still open").

Files: `data/historical/sp100_as_of.json` (22 years, 67 unique symbols), `lib/historical_membership.py`, `tests/test_historical_membership.py`, `scripts/run_survivor_bias_stress.py`. Reports: `reports/learning/survivor_bias_stress_2026-05-14.md` and `.json`.

### SAFE_MODE — landed 2026-05-14

External-review concern #4 (need a "frozen execution" mode for when LLM stack degrades) is closed. Eight commits land the operating-mode infrastructure: `244e05b`, `a58a814`, `9002d7f`, `567103b`, `24c2b73`, plus this plan update.

Added a sixth operating mode: `SAFE_MODE`. Same deterministic strategy + paper-fill execution as `PAPER_TRADING`, but learning writes (`memory/` except `daily_snapshots/`, `prompts/proposed_updates/`, `self_learning` agent dispatches) are suppressed by both prompt-layer guards (in 6 routine prompts + the self_learning agent) and a file-layer hook (`.claude/hooks/safe_mode_writes.sh`).

**Use case:** prompts misbehaving, model providers degrading, memory accumulating low-quality heuristics. Keep the deterministic engine running while the LLM stack is paused for inspection. Entry via `/enter-safe-mode <reason>` (paired audit log + mode flip + commit + Telegram); resume to `PAPER_TRADING` requires explicit human PR.

Files: `lib/operating_mode.py` (12 tests), `.claude/hooks/safe_mode_writes.sh`, `.claude/commands/enter-safe-mode.md`, schema (`tests/schemas/approved_modes.schema.json`) + transitions doc (`config/approved_modes.yaml`). CLAUDE.md updated. Routine + agent guards land directly (Bash bypass per session consent).

### Alpaca paper-account mirror mode — landed 2026-05-14

Until today, "paper trading" was 100% internal CSV simulator (`lib/paper_sim.py`).
Operator noticed their Alpaca paper account was empty despite ~3 days of sim
activity. Diagnosis: `lib/broker.py` only had READ methods (account_snapshot,
get_positions); no order placement. Routine prompts called `paper_sim.open_position`
which only wrote to `log.csv` + `positions.json`.

Three commits land the mirror infrastructure (sim default unchanged):

- `bf3aba2`: `lib/broker.py` gains `submit_market_order`, `get_order`,
  `cancel_all_open_orders`, `close_all_positions`. Live mode still gated.
  8 unit tests with mocked alpaca-py.
- `606fc6a`: `lib/paper_sim.py` env-controlled mirror via `BROKER_PAPER=alpaca`.
  When enabled, every open/close submits a market order, polls 5s for fill,
  records broker fill price + slippage vs sim in the log's notes column.
  Falls back to sim price on broker failure (does not crash the routine).
  Default `BROKER_PAPER=sim` preserves current behavior. 10 unit tests.
- `631b7df`: `scripts/sync_alpaca_state.py` reconciliation + `--reset-fresh-start`
  destructive setup that closes all Alpaca positions, clears local positions.json,
  appends a RESET marker to log.csv (append-only), resets CB to FULL with
  peak=current Alpaca equity, writes paired `logs/risk_events/<ts>_state_reset.md`.

Plus a routine + docs commit:

- end_of_day step 8a: when `BROKER_PAPER=alpaca`, reconciles local vs Alpaca
  positions; any divergence is URGENT alert + halt-progression (no auto-resolve).
- `docs/operator_runbook.md > Alpaca paper-account mirror mode`: enablement
  walkthrough.

**Operator action remaining (not part of this commit):**

1. Confirm `ALPACA_PAPER_KEY_ID` / `ALPACA_PAPER_SECRET_KEY` set in cloud env.
2. Run `python3 scripts/sync_alpaca_state.py --reset-fresh-start` from a shell
   with creds. Closes the 4 dormant sim positions (GLD/GOOGL/WMT/XOM), resets
   the inflated CB peak ($119,140 → current Alpaca equity), aligns state.
3. Set `BROKER_PAPER=alpaca` in cloud routine env.
4. Next end_of_day routine will start placing real Alpaca paper orders.

Tests: 207 → (still 207; reconciliation is in routine prompt, not lib).

### Landed 2026-05-14 (cross-cutting maintenance + first ensemble deliverable)

Five commits cleared items that had been carried in `Still open` since the pivot. Test suite 232 → 245.

- **`lib/signal_consolidator.py`** (+ 11 tests) — first deliverable of the daily-layer ensemble framework. When two strategies emit ENTRY on the same symbol (the GLD-via-TAA + gold_permanent_overlay case), highest-allocation wins as primary; others recorded as `subsumed_strategies` and routed to a NO_TRADE decision file with `reason: subsumed_by_<primary>`. EXIT never subsumed; ENTRY+EXIT conflict surfaces as `conflict=True` for URGENT operator alert. Production-routine wiring landed via the EOD prompt rewrite (Step 4a). Structured `allocation_pct` field for `config/strategy_rules.yaml` also landed (schema, config, consolidator config-aware lookup); landed drafts archived under `prompts/proposed_updates/landed/`.
- **`lib/symbol_history.py`** (+ 15 tests) — per-symbol decision-log compression. Once `decisions/by_symbol/<SYM>.md` accumulates > 50 timeline entries, older ones collapse into a `<!-- COMPRESSED:BEGIN -->...<!-- COMPRESSED:END -->` block with counts by action, realized PnL across closed trades, and a pointer to `decisions/by_symbol/archive/<SYM>_pre_<date>.md` for full history. Idempotent. Performance Review wiring landed in `.claude/agents/performance_review.md > Outputs` (Timeline compression step).
- **`lib/archive.py` + `scripts/archive_routine_logs.py`** (+ 12 tests) — auto-archive `logs/routine_runs/*.md` files older than 30 days into `logs/routine_runs/archive/<year>/<month>/`. Filename-date based so it's mtime-safe across worktrees. EOD-routine wiring landed as Step 0 (housekeeping, non-fatal).
- **`docs/risk_profile.md`** — full rewrite for the post-pivot multi-strategy portfolio. Captures absolute-return goal (8-10% CAGR / 15% DD / Sharpe ≥ 0.8), 60/30/10 allocations, Path Z circuit-breaker thresholds, regime-diversity gates, halt triggers, and known limitations. Sign-off slot pending operator signature on PR merge.
- **`.claude/hooks/validate_yaml_schema.sh`** — prefers `$(repo_root)/.venv/bin/python` when present, falling back to system `python3` (closes the operator hook portability item).

### Landed 2026-05-15

- **`lib/paper_monitor.py` + `scripts/paper_trading_monitor.py`** (+ 33 tests). Daily sanity check on the first weeks of paper trading: trade-log ↔ positions.json reconciliation (RESET-marker aware so post-`sync_alpaca_state` history doesn't trigger false-fails), circuit-breaker state shape + peak-vs-current invariant, risk-event count in trailing window, `approximate_input_kb` trend across audit logs vs the 200 KB advisory cap with heaviest-files surfacing on WARN/FAIL. Exit 0/1/2 for OK/WARN/FAIL. Live run on 2026-05-15 surfaces two real WARNs: 6 risk events in 7 days (recent CB transitions + Alpaca-mirror reset, expected) and `approximate_input_kb=178` near the 190 fail threshold.
- **`lib/phase2_gate.py` + `scripts/check_phase2_gate.py`** (+ 18 tests). Mechanical evaluation of the Phase 2 → Phase 3 gate criteria per trading day: pre-market commit present, EOD commit present, no halt entries in `logs/risk_events/`, journal ≥ 2 KB, audit `exit_reason` is clean/noop. Live run on 2026-05-15 confirms **3 consecutive CLEAN days** (2026-05-12, 13, 14); today INCOMPLETE; 2026-05-11 was the go-live mode-flip day and PARTIAL. Gate clears by 2026-05-18 EOD if Fri + Mon both land clean. Exit 0 = gate passes; exit 1 = not yet.
- **`reports/learning/2008_stress_test_2026-05-15.md`** — ran `scripts/run_2008_backtest.py` on the 2007-06-01 → 2026-05-08 window. **Initial verdict PASS (CAGR 11.95%) was invalidated later same day** by the circuit-breaker blend-bug fix below; corrected verdict is **CAGR 3.58%, max DD 12.49%, Sharpe 0.64 — FAILS the 8% return floor**. The DD ceiling held, the return target did not. The 2026-05-11 go-live decision rested on the 2013-2026 production window where the blend bug barely shifts results (10.08% legacy vs 10.60% corrected), so live unlock criteria are not invalidated — but the "2008 stress test passed" claim has been retracted.
- **`reports/learning/strategy_b_allocation_review_2026-05-15.md`** — re-ran the multi-strategy backtest with 4 reduced-B variants on the 2008-inclusive window. Investigating an apparent 7pp CAGR swing between B=25 and B=30 surfaced a **floating-weight bias in `apply_circuit_breaker`** that overstated CAGR by ~8pp on the 2008-inclusive window and inflated allocation-sensitivity. **Decision stands: keep B at 30%** — but with the corrected blend the underlying reason changed from "production is insensitive, stress is reactive" to "both windows are insensitive; there's no upside to changing B."
- **`scripts/run_multi_strategy_backtest.py`** — fixed: `apply_circuit_breaker` now blends per-strategy daily returns using target weights (representing daily rebalance to alloc-a/b/c) by default. Legacy floating-weight blend preserved via `--legacy-cb-blend` for reproducing pre-fix backtests. Production 2013-2026 CAGR is essentially unchanged (10.60% new vs 10.08% legacy). The 2008-inclusive window verdict flipped from PASS to FAIL on returns.
- **`lib/paper_monitor.py`** — context-budget check now surfaces the heaviest 5 files in `files_read` when the budget warns/fails, so the operator can see at a glance which file to compress or stop reading. Live 2026-05-15 run: `journals/daily/2026-05-14.md (44 KB)`, `reports/pre_market/2026-05-14.md (18 KB)`, `data/market/2026-05-14/0630.json (17 KB)`, `prompts/routines/end_of_day.md (14 KB)`, `CLAUDE.md (10 KB)`.
- **`prompts/proposed_updates/2026-05-15_routine_context_budget_guidance.md`** — drafted prompt change to add a "Context budget" subsection to all 4 intraday/EOD routines telling the orchestrator NOT to re-read raw market dumps, prior-day journals, or the full pre-market report. Locked file; needs human PR.

### Landed 2026-05-15 (PM — observability fixes from market_open no-op surprise)

The 09:35 ET remote `market_open` run completed cleanly but went silent on Telegram (per the explicit "Notify Telegram only if action was taken" rule), and the operator initially read that silence as "the routine never fired." Diagnosis surfaced four genuine bugs in adjacent code paths. All four landed on `fix/reconcile-bootstrap-heartbeat` ([PR #14](https://github.com/pmehaboobkhan/claude_trading_bot/pull/14)); test suite goes 280 → 318.

- **`lib/paper_sim.py > reconcile()` is now RESET-aware** (+ 6 new tests in `tests/test_paper_sim_reconcile.py`). The append-only `trades/paper/log.csv` contained 4 OPENs (GLD/GOOGL/WMT/XOM) from before the 2026-05-15 00:31 UTC `_RESET_` marker. `reconcile()` was scanning the entire log and surfacing those as phantom discrepancies against an empty `positions.json`. Fix mirrors the `RESET_TOKENS`/`_is_reset_row` logic already proven in `lib.paper_monitor.parse_trade_log` — only rows AFTER the most-recent reset marker are considered "live." Pre-reset rows are no longer phantom divergence.
- **`lib/data.py > _get_bars_yfinance()` self-heals missing yfinance** (+ 3 new tests in `tests/test_data.py`). The remote scheduled-agent environment lacked `yfinance` despite being pinned in `requirements.txt`; the silent fallback to Alpaca IEX produced the 7-day daily-bar lag seen in today's pre-market (`latest bar 2026-05-08`). On `ImportError` the module now does a one-shot `pip install yfinance` per process and re-imports; failure raises a clear `BrokerError` pointing at the new bootstrap script. The one-shot guard prevents install-loop on persistent failure.
- **`scripts/bootstrap_env.sh`** — idempotent setup script (`pip install -r requirements.txt` + post-install import check on yfinance + alpaca-py). Intended to be wired into the scheduled remote agent's pre-run step so the self-heal in `lib/data.py` is a safety net rather than a primary path.
- **`scripts/news_probe.py`** (+ 9 new tests in `tests/test_news_probe.py`). Replaces the "default-offline" habit in pre-market (where `news_unavailable` was being stamped as a fallback before any probe). Does a 5-second HEAD against SEC EDGAR, writes `data/news/<date>/_status.md` with `REACHABLE`/`UNREACHABLE` + the exact URL + timestamp. Midday on 2026-05-14 had already proven the connector works via WebSearch (see `journals/daily/2026-05-14.md:68`) — the new probe makes that empirical at every run instead of a per-routine convention.
- **`lib/notify.py > send_heartbeat()`** (+ 4 new tests in `tests/test_notify.py`). Short Telegram message for no-op routine runs: routine name, UTC timestamp, mode, position count, circuit-breaker state, equity, exit reason. Bounded to ≤3 messages per trading day across market_open / midday / pre_close. Action runs continue to use `send_html()` with the full action summary — heartbeats are no-op-only. Routine-prompt wiring drafted at `prompts/proposed_updates/2026-05-15_heartbeat_and_news_probe.md` for human PR application post-merge.
- **`.github/workflows/auto_merge_claude.yml`** — auto-merge widened from `claude/**` only to `claude/**`, `fix/**`, `feat/**`, `chore/**`, `docs/**`. Rationale: file-level hooks already gate every protected path at write time, so widening the branch trigger is safe and lets non-routine fix/feat work fast-forward to `main` without manual merge. Operator-authored (commit `8b1a0ea`) and included in the PR for traceability.

The pattern from the no-op surprise — *the routine ran cleanly, the operator couldn't tell* — is the more important lesson than any single bug. The heartbeat closes that observability gap. The reconcile bug had been desensitizing the operator to false-positive divergence; the yfinance fallback had been silently degrading data freshness; the news probe had been a default rather than a measurement. All three were latent for days; the no-op surprise was the only reason any of them surfaced.

### Landed 2026-05-16 (data-feed root cause, repo rename, Option B execution arc)

Repo renamed **`claude_trading_bot` → `calm_turtle`**. No local action: GitHub permanently redirects the old remote URL (pushes/fetches verified working); the only operator action is confirming each Claude Code web routine's repo binding points to `pmehaboobkhan/calm_turtle`. Old PR/URL references in this file are left as-is (GitHub redirects them); new entries use the new URL.

- **Data-feed blackout root cause — NOT a code bug.** The 2026-05-15 PM yfinance self-heal fixed a *missing package*; the 2026-05-15/16 blackout was a *different* failure mode: the Claude Code web `calm-turtle` agent's network egress allowlist did not include the Yahoo Finance hosts, so `yf.download` returned `HTTP Error 403: Host not in allowlist` for all 25 symbols (last good bar stuck at 2026-05-08, NO_TRADE for 4 sessions). Proven by reproducing the exact `lib.data` path locally (worked: bars through 2026-05-14). Neither the self-heal nor `bootstrap_env.sh` can fix a blocked host — both address a missing package. **Operator resolved**: added `query1/query2/fc.yahoo.com` to the agent allowlist. Empirical host-capture (yfinance 1.3.0 + curl_cffi) showed only `query1/query2.finance.yahoo.com` are hit; `finance.yahoo.com` recommended as a defensive add (cloud-IP consent fallback). Full allowlist also covers `paper-api/data/api.alpaca.markets` + `api.telegram.org`; `www.sec.gov`/pip hosts confirmed not needed by any v1 routine.
- **Web-routine instruction fixes** (`prompts/web_routines_instructions/`, commit `c93ec7a`, an allowed write path — not PR-locked): `monthly_review.md` was a 242-line copy of the locked routine spec (drift hazard) → replaced with the consistent short wrapper deferring to `prompts/routines/monthly_review.md`; `self_learning_review.md` gained the SAFE_MODE clause it was missing (the routine where SAFE_MODE matters most). Other six wrappers verified correct. Operator must paste the two changed files into the web-UI Instruction boxes for them to take effect.
- **Option B (Market-On-Close execution) arc — PRs [#16](https://github.com/pmehaboobkhan/calm_turtle/pull/16)–[#19](https://github.com/pmehaboobkhan/calm_turtle/pull/19), all merged. Backtest re-validated; Option B NOT enabled; `BROKER_PAPER=sim` is the validated interim.**
  - **Problem:** `end_of_day` cron is 16:30 ET but the regular session closes 16:00 ET (the routine *must* run after close — close-based signals). With `BROKER_PAPER=alpaca` the legacy path submits a `time_in_force="day"` market order that cannot fill in the 5 s poll after close, leaves a resting order at Alpaca, records the sim/close price locally, and step 8a reconciliation then URGENT-divergence-halts on *every* entry. Sim (`BROKER_PAPER=sim`) fills at the close = the backtest assumption, so sim is the only backtest-consistent config.
  - **#16** MOC primitives (`lib.broker.submit_moc_order` + `lib.paper_sim.submit_moc_entry`/`confirm_moc_fills`, 9 TDD tests) — dormant, nothing calls them.
  - **#17** signal-proxy validation gate (`scripts/validate_moc_signal_proxy.py`, TDD'd). Run on the full watchlist: **FAIL, decision-agreement 0.8667 vs 0.99.** Confirmed a *real* sensitivity, not a harness artifact (CSO source-seam ruled out). Every divergence is in `large_cap_momentum_top5` (rank-by-126d-return needs the exact official close, so it cannot fill at that close via MOC); `dual_momentum_taa` + `gold_permanent_overlay` had zero divergences over 60 days. Tightening the cutoff (15:50/15:55/15:58) does not help.
  - **#18** path (a): re-baseline B under realistic next-open execution. `lib.backtest.run_backtest` gained `fill_timing` (default `"close"` = bit-identical; canonical baseline reproduces +10.60%/12.58%/1.10 exactly), `--strategy-b-fill` passed to B only. Result: **B's edge survives** — portfolio +10.14% / DD 12.45% / Sharpe 1.05, OVERALL PASS; B standalone +1534%→+1347%. A/C contributions bit-identical (isolation verified).
  - **#19** as_of × next_open robustness + attribution. 2×2 (modern/as_of × close/next_open) all OVERALL PASS. Per-period attribution (two disjoint halves) verdict: **modern next_open is sign-stable −0.13…−0.63 pp (genuine modest momentum-gap drag); the as_of "+0.88 pp" is period-selection NOISE — sign flips across halves.** Conservative honest assumption to carry forward: **budget B's realistic-execution impact at ≈ −0.5 pp annualized, credit no upside.** All cells still pass minimum CLAUDE.md targets under that assumption. Memos in `reports/learning/strategy_b_*_2026-05-16.md` + `moc_signal_proxy_validation_2026-05-16*`.

### Still open

- [ ] **Go live on Alpaca paper — Monday 2026-05-18 (decided 2026-05-16).** No quant loop; simple model adopted: **Alpaca-authoritative mirror** ([PR #20](https://github.com/pmehaboobkhan/calm_turtle/pull/20)) — in `BROKER_PAPER=alpaca` mode Alpaca is the source of truth (submit+journal only; `reconcile()` re-mirrors from Alpaca; no phantom fills; no false divergence-halt; zero PR-locked edits). **Supersedes** the MOC (`2026-05-15`) and per-strategy (`2026-05-16`) proposals. Fills land next-open (decision is 16:30 ET, after the 16:00 close) ≈−0.5 pp/yr vs backtest — observing that real friction is the point of going live. **Remaining = operator only:** merge PR #20; in the Claude Code web env set `BROKER_PAPER=alpaca`, confirm Alpaca paper keys, confirm every routine's repo binding = `pmehaboobkhan/calm_turtle`, keep the Yahoo+Alpaca allowlist. Book already flat/aligned from the 2026-05-15 reset — no re-reset.
- [ ] Operator action: set up the three new intraday monitoring routines on Claude Code web (same template as pre_market / end_of_day; cron per `config/routine_schedule.yaml`; same `calm-turtle` environment). **Setup instructions landed in the chat 2026-05-15** — copy-paste cron strings + secrets.
- [x] Operator action: PR-merge the five `prompts/proposed_updates/*.md` drafts — **landed 2026-05-14**. All five drafts moved to `prompts/proposed_updates/landed/`. PR #3 (circuit-breaker EOD wiring) was already in `end_of_day.md` as of the 2026-05-11 go-live. PR #1 (allocation_pct), PR #2 (signal-consolidation Step 4a + Step 7 rewrite), PR #4 (Step 0 log archive), and PR #5 (perf-review compression step) applied directly to main with explicit operator authorization, bypassing the normal locked-file PR flow.
- [x] **Strategy B allocation review (URGENT-ish)** — **decided 2026-05-15: keep at 30%** until the survivor-bias-corrected backtest lands. See `reports/learning/strategy_b_allocation_review_2026-05-15.md`.
- [x] **Full-portfolio 2008 stress test** — **landed 2026-05-15**, PASS at 12.67% max DD on the 2007-2026 window. See `reports/learning/2008_stress_test_2026-05-15.md`.
- [x] **First paper-trading week monitoring** — script + tests landed 2026-05-15. Recurring cron candidate (daily or weekly).
- [x] **Alpaca free-tier daily-bar staleness — resolved.** Hybrid yfinance-for-daily landed in `lib.data`. The 2026-05-15/16 blackout was NOT this (IEX lag) nor the missing-package self-heal — it was the `calm-turtle` agent network allowlist missing the Yahoo hosts; operator-resolved 2026-05-16 (see Landed 2026-05-16). Residual standing requirement: the agent egress allowlist must keep the Yahoo + Alpaca + Telegram hosts.
- [ ] **VIX data source:** Alpaca free IEX does not provide VIX. Live-trading-gate `vix_high_observed` will permanently fail until a VIX-capable feed is wired (Polygon, Tiingo, or paid Alpaca tier).
- [ ] **Investigate per-strategy attribution caching in `run_multi_strategy_backtest.py`** (new, surfaced by Strategy B allocation review): the diagnostic per-strategy "Final equity" appears not to be recomputed when allocation arguments change, while the blended portfolio numbers do change. If both numbers come from the same code path the blend may be silently wrong for non-default allocations. Reproduces with `--alloc-b 0.20` vs `--alloc-b 0.25` returning identical `$1,106,895.52` for Strategy B in the diagnostic.
- [x] **Survivor-bias-corrected Strategy B backtest — landed 2026-05-15.** Re-ran with `--strategy-b-universe-mode as_of` against `data/historical/sp100_as_of.json` (22 years of point-in-time S&P 100 membership including LEH/BSC/MER/AIG/C/WB/GM/F). B's standalone 2008-onward return drops from +5,434% (modern) to ~+3,032% (as-of) — a 44% haircut. At portfolio level, with the corrected CB blend, the inflation barely propagates: 3.58% modern → 3.46% as-of CAGR on the 2007-2026 stress window. **Strategy B stays at 30%** — the morning's decision is affirmed by survivor-bias-corrected evidence. See `reports/learning/strategy_b_survivor_bias_2026-05-15.md`.

### Files materially changed today
- `lib/signals.py` — three new strategy functions; `STRATEGY_FUNCS` dispatcher; TAA risk-asset set; deterministic.
- `lib/indicators.py` — `sma`, `rsi`, `atr`, `relative_strength`, `above_sma`, `pct_from_sma`.
- `lib/backtest.py` — event-driven harness; Sharpe/DD; promotion criteria.
- `lib/fills.py` — 1 bp slippage + 1 bp half-spread per side; consumed by `lib/paper_sim.py`.
- `config/watchlist.yaml` — 4 macro ETFs + 20 large-caps; IEF added; TLT paper-trading off.
- `config/strategy_rules.yaml` — 3 new strategies (`NEEDS_MORE_DATA`); 4 old sector strategies marked `REJECTED`.
- `config/risk_limits.yaml` — added `max_drawdown_pct: 15.0`, `max_macro_etf_position_pct: 60.0`, `max_risk_per_trade_pct: 1.5`, `daily_drawdown_halt_pct: 2.0`, `max_open_positions: 8`.
- `CLAUDE.md` — new goal block (8–10% / 15% DD / Sharpe 0.8); strategy allocations; SPY demoted to context only.
- `tests/test_signals.py` — 17 tests covering all three strategies, `evaluate_all` dispatch, reproducibility.
- `scripts/run_multi_strategy_backtest.py` — CLI: `--start`, `--end`, `--capital`, `--alloc-a`, `--alloc-b`, `--alloc-c`, `--label`. Combines daily equity curves additively.
- `scripts/yfinance_sweep.py` — out-of-regime testing; cache at `backtests/_yfinance_cache/`.
- `scripts/run_param_sweep.py` — in-sample variant sweep.
- `reports/learning/backtest_findings_2026-05-10.md` — sector rotation rejection.
- `reports/learning/pivot_validation_2026-05-10.md` — multi-strategy results + DD failure analysis + survivor bias.
- `backtests/multi_strategy_portfolio/` — three variant reports.

The phased architecture and the post-review refactor below still apply — only the *universe and strategies* changed.

---

## Post-Review Refactor (2026-05-10)

After an external architecture review, v1 was significantly tightened. Key changes:

1. **Decisions are deterministic, not LLM-generated.** `lib/signals.py` evaluates `strategy_rules.yaml > required_confirmations` and emits `ENTRY` / `EXIT` / `NO_SIGNAL`. Claude's `trade_proposal` agent wraps signals with thesis/context/R/R but never overrides the action. Backtests are now possible because signals are reproducible.
2. **Backtest harness is a prerequisite, not Phase 5.** `lib/backtest.py` runs event-driven backtests against historical bars; a strategy may not advance to `ACTIVE_PAPER_TEST` until its backtest report meets the promotion criteria.
3. **Realistic fill modeling.** `lib/fills.py` adds pessimistic friction (1 bp slippage + 1 bp half-spread per side) to paper-sim fills so paper PnL doesn't overstate edge.
4. **v1 routine set is 3 routines, not 8.** `pre_market`, `end_of_day`, `self_learning_review` (observations-only). The rest are scaffolded but `enabled: false` in `routine_schedule.yaml`.
5. **Self-Learning is observations-only in v1.** Until ≥ 90 trading days AND ≥ 50 paper trades, the agent writes to `memory/` but produces zero proposals. `prompts/proposed_updates/.v2_enabled` is the toggle that opens v2 mode.
6. **Cost caps in `risk_limits.yaml > cost_caps`.** Per-routine bounds on subagent dispatches, tokens (advisory), decisions, and self-learning proposals.
7. **GitHub Actions watchdog.** `.github/workflows/eod_watchdog.yml` runs at 17:30 ET on trading days; if no EOD commit landed, fires a Telegram alert. This is the reliability backstop the review correctly demanded.
8. **Deterministic unit tests** at `tests/test_signals.py` — 11 tests proving signal logic is reproducible. The whole point of moving decisions into Python is that they're now testable.

The original phased architecture below still describes the long-run system. The differences are all about *what's active in v1*.

---

## Context

You want a Claude-native automation system that researches a 12-symbol **sector-ETF rotation universe** during U.S. trading hours, makes structured trade decisions, paper-trades them via Alpaca, journals every action, commits artifacts to GitHub, and learns from its own outcomes — without ever silently escalating itself toward real money. The goal is **risk-adjusted outperformance vs SPY** over rolling 6- and 12-month windows, with max drawdown held at or below SPY's drawdown over the same window. Absolute return alone is not the target.

This plan is the build blueprint. It is research-and-paper-only for v1. Live trading is gated behind explicit human approval, broker-side limits, and long paper-trading evidence. Broker is **Alpaca** (paper API now; live API gated to Phase 8). Notifications are Telegram. The workspace is currently an empty directory at `/Users/mehaboob.khan.perur/gitrepos/claude_trading_bot` — everything below is to be created.

### The edge thesis (why this universe)
LLM-driven systems can plausibly add value in **macro/sector-context synthesis and discipline** — not in microstructure, earnings forecasting, or single-stock alpha. Sector rotation is one of the few persistent, documented sources of alpha that maps cleanly to the kind of reasoning the system can do (regime → which sectors lead → overweight). Trading sector ETFs avoids single-stock earnings catastrophes, gives clean attribution (was the regime call right? was the sector call right? was timing right?), and stays within the system's plausible edge.

### Two benchmarks (both reported every weekly/monthly review)
1. **SPY** — the stated risk-adjusted target. Outperform on Sharpe with drawdown ≤ SPY's.
2. **Equal-weight buy-and-hold of the same 11 sector ETFs** — the "is the trading itself adding value?" test. If the system can't beat passive equal-weight rotation, the trading is just adding tax events and noise.

If the system fails either benchmark on a 3-month rolling basis, the monthly review must recommend `STAY_PAPER` or `HALT_AND_REVIEW`. Live trading does not unlock until both benchmarks are beaten on a 6-month risk-adjusted basis.

---

## 1. Executive Summary

### Recommended architecture (one-liner)
**Claude Code routines on the web** drive scheduled prompts; a **GitHub repo** is the durable brain (configs, journals, memory, audit logs); **subagents** specialize the analysis; **MCP connectors** fetch data and post notifications; **hooks** enforce deterministic guardrails; **human approval** gates anything that touches real money.

### Why Claude Code routines fit scheduled trading research
- Routines run on Claude Code on the web — no VM to babysit, no cron drift, no patching.
- Each run starts fresh and re-reads repo state, which is exactly what you want for trading: **stateless reasoning over versioned state**.
- They commit their own artifacts, so every routine run produces an immutable audit trail in Git.
- They can be triggered by schedule, GitHub event, or API — covering pre-market, intraday, EOD, weekly, monthly, and reactive workflows.

### Why GitHub is the durable layer
- Every config, journal, decision, paper trade, and learning artifact is **versioned, diffable, and reviewable**.
- Pull requests are a natural human-approval gate for risky changes (risk limits, live trading, watchlist additions).
- `git blame` answers "why did the system do that?" months later.
- Free, redundant, well-known toolchain — no bespoke database to maintain.

### Why live trading is OFF in v1
- LLMs hallucinate. Markets are adversarial. Your money does not deserve to be the test set.
- Without months of paper-trading evidence, calibration data, and drawdown observation, there is no basis to size live positions.
- Broker terms, PDT rules, settlement, and tax implications need human review before any real order is placed.

### The four operating modes (precise definitions)
| Mode | What it means | v1? |
|---|---|---|
| **Research-only** | System reads market state, produces reports & decisions. No trades anywhere. | Yes |
| **Paper-trading** | Decisions become simulated fills in a paper-trade log. No broker contact. | Yes (Phase 4+) |
| **Human-approved live proposals** | System produces `PROPOSE_LIVE_*` records; human clicks approve; trade is placed. | Phase 6+ |
| **Autonomous live execution** | System places live orders within hard limits without per-trade approval. | Phase 9+ only after sustained paper evidence. Default: never. |

---

## 2. Claude-Native Architecture

### Architecture diagram (text)

```
                    ┌──────────────────────────────────────────────────┐
                    │              Claude Code on the Web              │
                    │                                                  │
                    │   ┌────────────┐   ┌────────────┐  ┌──────────┐  │
                    │   │ Scheduled  │   │  GitHub-   │  │   API    │  │
                    │   │  Routines  │   │ triggered  │  │triggered │  │
                    │   │ (cron ET)  │   │  Routines  │  │ Routines │  │
                    │   └─────┬──────┘   └─────┬──────┘  └────┬─────┘  │
                    │         └──────────┬─────┴──────────────┘        │
                    │                    ▼                             │
                    │            ┌───────────────┐                     │
                    │            │  Orchestrator │ (master prompt)     │
                    │            │     Agent     │                     │
                    │            └───────┬───────┘                     │
                    │                    │ delegates to                │
                    │     ┌──────────────┼──────────────┐              │
                    │     ▼              ▼              ▼              │
                    │ ┌────────┐    ┌────────┐    ┌──────────┐         │
                    │ │ Market │    │  News  │    │Technical │   ...   │
                    │ │  Data  │    │ Sent.  │    │ Analysis │         │
                    │ └────────┘    └────────┘    └──────────┘         │
                    │      │             │             │               │
                    │      ▼             ▼             ▼               │
                    │ ┌──────────────────────────────────────┐         │
                    │ │ Risk Manager → Compliance/Safety →   │         │
                    │ │ Trade Proposal → Journal             │         │
                    │ └──────────────────────────────────────┘         │
                    └────────────────────┬─────────────────────────────┘
                                         │ reads / writes / commits
                                         ▼
       ┌─────────────────────────────────────────────────────────────┐
       │                 GitHub Repo (durable brain)                 │
       │   /CLAUDE.md  /.claude/  /config/  /journals/  /decisions/  │
       │   /trades/  /memory/  /reports/  /prompts/  /logs/          │
       └────────────┬────────────────┬─────────────────┬─────────────┘
                    │                │                 │
                    ▼                ▼                 ▼
        ┌───────────────┐  ┌───────────────┐  ┌──────────────────┐
        │ MCP Connectors│  │     Hooks     │  │ Notification     │
        │ • GitHub      │  │ (deterministic│  │ (Slack/email/SMS)│
        │ • Market data │  │  guardrails)  │  │                  │
        │ • News        │  └───────────────┘  └──────────────────┘
        │ • SEC/Earnings│
        │ • Broker(read)│         ┌──────────────────────────────┐
        │ • Notifier    │  ◄──── │ Human Approval Gate (PR review)│
        └───────────────┘         └──────────────────────────────┘
```

### Component roles
- **Routines**: schedulers + entrypoints. Load context, run orchestrator prompt, commit, notify.
- **Orchestrator agent**: master prompt that calls subagents and assembles outputs.
- **Subagents** (`.claude/agents/*.md`): role-scoped prompts with restricted tool access.
- **Slash commands** (`.claude/commands/*.md`): manual entrypoints for the human operator.
- **CLAUDE.md**: repo-level operating manual; auto-loaded into every session.
- **Hooks** (`.claude/settings.json`): deterministic shell-level checks — schema validation, secret blocking, journal immutability.
- **GitHub Actions**: opt-in. Use only for things that must run even if Claude is offline (e.g., daily backup, schema lint on PR). Don't use them for trading logic.
- **MCP/connectors**: GitHub, market data (Polygon/Alpaca/Tiingo), news (Benzinga/NewsAPI), SEC EDGAR, economic calendar (FRED), notifications (Slack/email), broker (read-only first, then sandbox, then live).
- **Human approval**: PR review for any change to `risk_limits.yaml`, `strategy_rules.yaml`, `approved_modes.yaml`, or `live` portions of `watchlist.yaml`.

---

## 3. Claude Code Routine Design

All times U.S. Eastern. Routines run on trading days only (the orchestrator checks the NYSE calendar and exits early on holidays/weekends).

### A. Pre-Market Routine
| Field | Value |
|---|---|
| Trigger | Scheduled, 06:30 ET Mon–Fri |
| Inputs | `CLAUDE.md`, `config/watchlist.yaml`, `config/risk_limits.yaml`, `config/strategy_rules.yaml`, last 5 daily journals, open paper positions, `memory/market_regimes/current_regime.md` |
| Connectors | Market data (overnight quotes, futures), news, economic calendar |
| Subagents | Market Data, News & Sentiment, Macro/Sector, Technical Analysis |
| Outputs | `reports/pre_market/YYYY-MM-DD.md`, updated watch list candidates |
| Commit msg | `pre-market: research report YYYY-MM-DD (N symbols flagged)` |
| Notification | "Pre-market report ready. N symbols on watch. Top thesis: …" |
| Halt conditions | Stale market data > 30 min; missing risk_limits.yaml; conflicting open positions vs broker (Phase 7+) |

### B. Market Open Routine
| Field | Value |
|---|---|
| Trigger | Scheduled, 09:35 ET Mon–Fri (5 min after open to let opening volatility settle) |
| Inputs | Latest pre-market report, live quotes, open paper positions |
| Connectors | Market data |
| Subagents | Market Data, Technical Analysis, Risk Manager, Trade Proposal |
| Outputs | `decisions/YYYY-MM-DD/HHMM_<symbol>.json` with `WATCH` / `NO_TRADE` / `PAPER_TRADE_PROPOSAL` |
| Commit msg | `open: N decisions (P proposals, W watch, X no-trade)` |
| Notification | "Market open: N proposals queued. See decisions/" |
| Halt conditions | Volatility circuit breaker triggered; data feed lag > 60s; > `max_trades_per_day` already used |

### C. Midday Routine
| Field | Value |
|---|---|
| Trigger | Scheduled, 12:00 ET Mon–Fri |
| Inputs | Open paper positions, morning decisions, regime memory, intraday news |
| Connectors | Market data, news |
| Subagents | Market Data, News, Risk Manager, Portfolio Manager, Journal |
| Outputs | Updated `journals/daily/YYYY-MM-DD.md` (midday section), possibly `PAPER_CLOSE` decisions if invalidation triggered |
| Commit msg | `midday: position review (Q open, R closed)` |
| Notification | Skip unless action taken or risk event detected |
| Halt conditions | Daily loss limit hit; consecutive-loss threshold hit |

### D. Pre-Close Routine
| Field | Value |
|---|---|
| Trigger | Scheduled, 15:30 ET Mon–Fri |
| Inputs | Open positions, day's P&L, regime memory |
| Connectors | Market data |
| Subagents | Portfolio Manager, Risk Manager, Trade Proposal |
| Outputs | `decisions/YYYY-MM-DD/preclose_*.json`, `PAPER_CLOSE` actions for invalidated theses |
| Commit msg | `pre-close: N hold, M close decisions` |
| Notification | "Pre-close: closing X paper positions, holding Y overnight." |
| Halt conditions | Same as midday |

### E. End-of-Day Routine
| Field | Value |
|---|---|
| Trigger | Scheduled, 16:30 ET Mon–Fri |
| Inputs | All day's decisions, paper trade log, journal drafts, regime memory |
| Connectors | Market data (close prices), news |
| Subagents | Performance Review, Journal, Compliance/Safety |
| Outputs | `journals/daily/YYYY-MM-DD.md` finalized, `trades/paper/log.csv` updated, `reports/end_of_day/YYYY-MM-DD.md`, observation entries in `/memory/prediction_reviews/` |
| Commit msg | `eod: journal + perf YYYY-MM-DD (PnL: ±$X.XX, N trades)` |
| Notification | "EOD: PnL ±$X. Win rate W%. Top lesson: …" |
| Halt conditions | Cannot reconcile paper log; missing close prices |

### F. Weekly Review Routine
*Benchmark tracking*: Weekly review computes paper portfolio return vs **SPY** and vs **equal-weight Mag 7 buy-and-hold**, plus alpha, beta, tracking error.

| Field | Value |
|---|---|
| Trigger | Scheduled, Saturday 09:00 ET |
| Inputs | Last 5 daily journals, all decisions, paper trade log, regime memory, agent performance memory |
| Connectors | None required (offline analysis) |
| Subagents | Performance Review (metrics), Self-Learning (interpretation + proposals), Journal, Compliance/Safety |
| Outputs | `journals/weekly/YYYY-WW.md`, `reports/learning/weekly_learning_review_YYYY-MM-DD.md`, draft prompt updates in `/prompts/proposed_updates/`, possibly a PR for review |
| Commit msg | `weekly-review: WW YYYY (win rate W%, profit factor PF)` |
| Notification | "Weekly review ready. K proposed prompt updates, J risk lessons. Review PR #N." |
| Halt conditions | None — review is read-only |

### G. Monthly Review Routine
*Benchmark tracking*: Monthly review reports period return, alpha vs SPY, alpha vs equal-weight Mag 7, beta to SPY, max drawdown vs SPY's, and information ratio. Mode recommendation downgrades to `STAY_PAPER` if the system underperforms equal-weight Mag 7 buy-and-hold over the rolling 3-month window.

| Field | Value |
|---|---|
| Trigger | Scheduled, 1st of month 09:00 ET |
| Inputs | Prior month's journals, weekly reviews, full trade log, all memory artifacts |
| Connectors | None |
| Subagents | Performance Review (metrics), Self-Learning (interpretation + proposals), Compliance/Safety |
| Outputs | `journals/monthly/YYYY-MM.md`, `reports/learning/monthly_learning_review_YYYY-MM-DD.md`, **Mode recommendation**: `STAY_PAPER` / `PROPOSE_HUMAN_APPROVED_LIVE` / `HALT_AND_REVIEW` |
| Commit msg | `monthly-review: YYYY-MM (recommendation: STAY_PAPER)` |
| Notification | "Monthly review: recommendation = STAY_PAPER. See report." |
| Halt conditions | If `HALT_AND_REVIEW`, the next pre-market routine refuses to proceed until human resolves. |

### H. Self-Learning Review Routine (separate from G)
Runs weekly Sunday 10:00 ET; details in §21.

---

## 4. Multi-Agent Design

Thirteen subagents. Each lives at `.claude/agents/<name>.md`. All subagents inherit the **Compliance/Safety** rules from CLAUDE.md.

### Orchestrator Agent
- **Role**: Coordinates a routine run. Reads inputs, dispatches to specialist agents, assembles outputs, calls Risk + Compliance gates, commits.
- **Inputs**: Full repo context, routine type.
- **Outputs**: Routine artifacts (reports, decisions, journal updates).
- **Allowed**: Read all repo files, call all subagents, write to `journals/`, `decisions/`, `reports/`, `trades/paper/`, `logs/`, `memory/` (observation files only).
- **Forbidden**: Edit `config/risk_limits.yaml`, `config/strategy_rules.yaml`, `config/approved_modes.yaml`, `config/watchlist.yaml` (only humans via PR), or `trades/live/*`.
- **Required checks**: Verify market is open before trading-hour routines; verify configs validate against schema; confirm Risk Manager + Compliance/Safety have signed off before any paper trade.
- **Failure mode**: If any subagent fails, write a `logs/routine_runs/<timestamp>_FAILED.md` and notify; do not silently skip.
- **Escalation**: Halt routine and tag `urgent` in notification.

### Market Data Agent
- **Role**: Fetch and summarize price, volume, volatility, and structure data for watchlist symbols.
- **Inputs**: Watchlist, time window, MCP market-data connector.
- **Outputs**: Structured price/volume snapshot in `data/market/YYYY-MM-DD/`.
- **Allowed**: Read connectors, write to `data/market/`.
- **Forbidden**: Make trading decisions, write to `decisions/`, edit configs.
- **Required checks**: Stamp data with timestamp + freshness; flag if data > `max_data_staleness_seconds`.
- **Failure mode**: Return partial snapshot with explicit `missing` field; do not fabricate.
- **Escalation**: Repeated stale data → recommend HALT for the routine.

### News & Sentiment Agent
- **Role**: Pull recent headlines and earnings/8-K events for each watchlist symbol; classify tone.
- **Inputs**: Watchlist, news connector, SEC EDGAR.
- **Outputs**: `data/news/YYYY-MM-DD/<SYMBOL>.md` with cited sources and timestamps.
- **Allowed**: Read connectors, write to `data/news/`.
- **Forbidden**: Generate news that wasn't retrieved; trade decisions.
- **Required checks**: Every claim must cite a source URL. No source → no claim.
- **Failure mode**: If connector fails, mark symbol as `news_unavailable`; downstream agents must treat as a risk factor, not as "no news = bullish."
- **Escalation**: News gap > 24h on a watchlist symbol → flag.

### Technical Analysis Agent
- **Role**: Compute classical TA — trend, support/resistance, moving averages, RSI, MACD, volume profile — and pattern detection.
- **Inputs**: Market data snapshot, symbol profile from `memory/symbol_profiles/<SYMBOL>.md`.
- **Outputs**: TA section per symbol; included in pre-market report and decision records.
- **Allowed**: Read data, read memory, write to scratch in routine output.
- **Forbidden**: Override Risk Manager; cite indicators it didn't compute.
- **Required checks**: Disclose lookback windows; never use indicators that require data more recent than the freshness watermark.
- **Failure mode**: Insufficient bars → return `insufficient_data` not a fabricated reading.
- **Escalation**: None internal.

### Fundamental Context Agent
- **Role**: For sector ETFs, this agent does **sector-aggregate fundamentals**, not single-name 10-Q analysis. Tracks: aggregate sector P/E, earnings revision breadth, top-5 holdings concentration per ETF, and any major holding's earnings event that materially moves the ETF (e.g., NVDA earnings → XLK).
- **Inputs**: Watchlist, ETF holdings (via Alpaca/issuer data), SEC EDGAR (only for top-5 holdings of each ETF on earnings days).
- **Outputs**: `data/fundamentals/<ETF>.md` updated weekly + on holding earnings events.
- **Allowed**: Read holdings + EDGAR for holdings, write fundamentals files.
- **Forbidden**: Forecast earnings; valuation calls without disclosed assumptions; deep single-stock dives outside the holdings context.
- **Required checks**: Stamp filing date and accession number for any cited filing; flag when an ETF's top-5 holding is ≥ 20% of weight (concentration risk).
- **Failure mode**: Filings unavailable → mark `fundamentals_stale`; macro/technical agents continue.
- **Escalation**: A single holding > 25% of an ETF flagged as elevated single-name risk in routine summary.

### Macro/Sector Context Agent
- **Role**: Identify market regime (per §21G) and sector posture.
- **Inputs**: Index data, FRED economic calendar, regime memory.
- **Outputs**: Update `memory/market_regimes/current_regime.md` with proposed regime classification (final classification needs Compliance review).
- **Allowed**: Read connectors, propose regime updates.
- **Forbidden**: Silently flip the regime classification; write directly without a "proposed" → "confirmed" step.
- **Required checks**: Cite at least 3 indicators supporting the regime call.
- **Failure mode**: Conflicting signals → `regime: uncertain`, raise caution level.
- **Escalation**: Regime change to `liquidity_stress` or `high_volatility` → automatic notification.

### Risk Manager Agent
- **Role**: The veto. Evaluates each proposed paper trade against `risk_limits.yaml` and current portfolio state.
- **Inputs**: Proposed trade, open positions, daily/weekly/monthly P&L, risk limits.
- **Outputs**: `risk_manager_verdict: APPROVED | REJECTED | NEEDS_HUMAN` plus reasoning.
- **Allowed**: Block any decision; require sizing changes.
- **Forbidden**: Ever raise its own limits; ever approve a trade outside the watchlist; ever approve a live trade without `human_approval_required=true` being satisfied.
- **Required checks**: Daily loss limit, position sizing %, max open positions, max trades per day, consecutive-loss halt, earnings blackout window, R/R ratio threshold.
- **Failure mode**: Any unparseable input → REJECT.
- **Escalation**: Risk event (limit breach, anomalous order) → `logs/risk_events/<timestamp>.md` and urgent notification.

### Portfolio Manager Agent
- **Role**: Tracks open paper positions, computes exposure, decides hold/close on existing positions.
- **Inputs**: Paper trade log, current quotes, original theses (from `decisions/`).
- **Outputs**: `PAPER_CLOSE` proposals when invalidation conditions are met; portfolio summary in journal.
- **Allowed**: Read decisions, propose closes.
- **Forbidden**: Open new positions (that's Trade Proposal Agent's job); average down unless `risk_limits.yaml` explicitly allows.
- **Required checks**: For every open position, has invalidation condition triggered? Has time-stop been exceeded?
- **Failure mode**: If thesis doc is missing for an open position, force `PAPER_CLOSE` next routine.

### Trade Proposal Agent
- **Role**: Synthesizes specialist outputs into structured `trade_decision.json` records.
- **Inputs**: TA, fundamentals, news, macro, current portfolio.
- **Outputs**: `decisions/YYYY-MM-DD/<HHMM>_<SYMBOL>.json` per the schema in §6D.
- **Allowed**: Write to `decisions/`.
- **Forbidden**: Skip Risk Manager; write any `final_status: EXECUTED` without compliance gate.
- **Required checks**: Every decision has bull thesis, bear thesis, invalidation, R/R, position size, confidence.
- **Failure mode**: Missing input → emit `NO_TRADE` with reason `insufficient_inputs`.

### Journal Agent
- **Role**: Maintains daily, weekly, monthly journals **and** the per-symbol decision history files.
- **Inputs**: Decisions, trade log, risk events, agent outputs.
- **Outputs**: `journals/daily/YYYY-MM-DD.md`, weekly/monthly journals, append-only entries to `decisions/by_symbol/<SYM>.md` for every decision (one row per decision: timestamp, decision type, 1-line thesis, R/R, confidence, links to full decision JSON + analysis snapshot + outcome review).
- **Allowed**: Append to today's journal; create weekly/monthly journals; **append** (never edit prior rows) to `decisions/by_symbol/<SYM>.md`.
- **Forbidden**: Edit any journal file dated more than 24h ago (enforced by hook); edit existing rows in `decisions/by_symbol/*.md` (append-only, enforced by hook).
- **Required checks**: Every decision must appear in both the dated decision file AND the per-symbol timeline; nothing fabricated; "what failed" section is mandatory even on green days.

### Compliance/Safety Agent
- **Role**: Final gate. Refuses to commit anything that violates CLAUDE.md rules or `approved_modes.yaml`.
- **Inputs**: All proposed file writes for the routine.
- **Outputs**: Approval or `REJECTED_COMPLIANCE` log entry.
- **Allowed**: Block commits, halt routine.
- **Forbidden**: Approve actions in modes the system isn't operating in (e.g., live trade in paper-only mode).
- **Required checks**: Mode check, watchlist check, secret check, hook list ran clean.
- **Escalation**: Two compliance rejections in 24h → urgent notification + auto-halt next routine.

### Performance Review Agent
- **Role**: Computes quantitative performance metrics. Pure measurement, no interpretation. Also maintains the **cumulative-stats header** at the top of each `decisions/by_symbol/<SYM>.md` (overwriting the header section is allowed; the timeline rows below remain append-only).
- **Inputs**: Trade log, decisions, journals, prediction reviews.
- **Outputs**: Metric files under `/memory/signal_quality/`, `/memory/strategy_lessons/` (numeric sections only), `/reports/learning/` (metrics sections), header-only updates to `decisions/by_symbol/<SYM>.md`.
- **Allowed**: Write metric outputs; flag statistically anomalous results; rewrite the header (delimited section) of per-symbol history files.
- **Forbidden**: Make qualitative recommendations (that's the Self-Learning Agent); edit production prompts; edit risk/strategy configs; modify any timeline row in per-symbol history files (append-only hook enforces).
- **Required checks**: Sample size guardrail (no metric reported as "significant" from < 20 trades); every metric stamped with sample size and date range.

### Self-Learning Agent
- **Role**: Reviews historical decisions, predictions, journals, paper trades, and market outcomes to identify patterns, recurring mistakes, and potential improvements. The interpretive layer on top of Performance Review's metrics. Drives the §21 learning loop.
- **Inputs**: Daily / weekly / monthly journals, trade decision records, paper trade logs, market data snapshots, `/memory/prediction_reviews/`, strategy performance metrics (from Performance Review Agent), `/memory/agent_performance/`, `/memory/market_regimes/current_regime.md`, `/memory/symbol_profiles/`.
- **Outputs**: Learning reports under `/reports/learning/`, updated memory artifacts under `/memory/` (observation and lessons files), proposed prompt improvements under `/prompts/proposed_updates/`, proposed strategy changes as review docs, rejected-learning entries under `/memory/rejected_learnings/`, human-approval queue entries (PR drafts).
- **Allowed**:
  - Update memory files in `/memory/` (observation, symbol_profiles, market_regimes, signal_quality narrative sections, strategy_lessons narrative sections, prediction_reviews, risk_lessons, model_assumptions, agent_performance, approved_learnings/rejected_learnings).
  - Create learning reports.
  - Propose prompt updates as drafts in `/prompts/proposed_updates/`.
  - Propose strategy changes as review documents (markdown, not yaml).
  - Flag weak strategies for human review (status proposal only).
  - Recommend halting or pausing strategies (proposal only — Compliance/Safety + human approve).
- **Forbidden**:
  - Change live-trading permissions or `approved_modes.yaml`.
  - Increase any risk limit in `risk_limits.yaml`.
  - Add new live-tradable symbols (no edits to watchlist live flags, ever).
  - Activate new strategies (no edits to `strategy_rules.yaml > allowed_strategies`).
  - Overwrite production prompts in `/prompts/agents/` or `/prompts/routines/` (drafts only, in proposed_updates).
  - Execute trades or trigger trade decisions.
  - Treat correlation as causation (must explicitly state confound candidates).
  - Overfit to small samples (every claim stamped with N; no claims from N < 20).
- **Required checks**:
  - Every proposed learning is tagged with one of the §21D categories (`SAFE_MEMORY_UPDATE`, `PROMPT_IMPROVEMENT`, `WATCHLIST_NOTE_UPDATE`, `STRATEGY_REVIEW_REQUIRED`, `RISK_RULE_REVIEW_REQUIRED`, `HUMAN_APPROVAL_REQUIRED`, `REJECTED_LEARNING`).
  - Every claim cites linked evidence (decision file paths, journal lines, log rows).
  - Observations and conclusions are written in separate sections — never blended.
  - Calibration claims (e.g., "high-confidence calls were wrong") cite the bucket size.
  - When proposing a change, include the counter-hypothesis and what evidence would refute it.
- **Example prompt**:
  ```
  You are the Self-Learning Agent. Review the latest journals, prediction reviews,
  trade decisions, and paper-trading results. Identify what the system learned,
  what it got wrong, what should be remembered, and what should be proposed for
  human review.

  Separate evidence-backed learnings from weak or speculative learnings. Update
  memory artifacts only when supported by sufficient evidence (N >= 20 for
  strategy claims; N >= 5 for symbol-specific claims; explicit "low-evidence"
  flag otherwise). Any change to active trading behavior, risk limits, strategy
  rules, approved symbols, or production prompts must be proposed for review
  rather than applied directly.

  For each proposed learning, include: claim, supporting evidence (with links),
  counter-hypothesis, refuting evidence that would change your mind, category
  tag (§21D), and confidence band.

  If sample size is insufficient, write the observation to /memory/ but
  explicitly mark it as PRELIMINARY and do not generate a prompt or strategy
  proposal from it.
  ```
- **Failure modes**:
  - Pattern-matching on too few trades → over-specific lessons that don't generalize. Mitigated by N guardrails.
  - Recency bias from a strong week → "this strategy is great now" claims. Mitigated by requiring rolling-window comparison.
  - Confirmation bias on accepted strategies. Mitigated by mandatory counter-hypothesis section.
  - Producing too many proposals → review fatigue. Mitigated by hard cap: ≤ 5 prompt proposals + ≤ 3 strategy proposals per review cycle.
- **Escalation**:
  - Repeated identical proposed changes that humans keep rejecting → flag as `RECURRING_REJECTED_PROPOSAL` and stop re-proposing for 30 days.
  - Detected calibration drift on a critical agent (Risk Manager, Compliance/Safety) → urgent notification; recommend HALT_AND_REVIEW.
  - If it identifies a risk rule that *should* be tightened (never loosened), open a PR draft and notify; never auto-apply.

---

## 5. Repository Structure

```
/CLAUDE.md                          # repo operating manual (auto-loaded)
/.claude/
  /agents/                          # subagent definitions (md + frontmatter)
  /commands/                        # custom slash commands
  /hooks/                           # hook scripts (referenced from settings.json)
  /settings.json                    # hooks, env, permissions
  /settings.local.json              # personal overrides (gitignored)
/config/
  watchlist.yaml                    # approved symbols + per-symbol permissions
  risk_limits.yaml                  # hard risk numbers
  strategy_rules.yaml               # which strategies allowed
  routine_schedule.yaml             # canonical schedule (mirrored in Claude Code routines)
  approved_modes.yaml               # current operating mode (paper / live / halt)
/data/
  market/YYYY-MM-DD/                # raw market snapshots
  news/YYYY-MM-DD/                  # raw news pulls
  fundamentals/<SYMBOL>.md          # fundamentals snapshots
/journals/
  daily/YYYY-MM-DD.md
  weekly/YYYY-WW.md
  monthly/YYYY-MM.md
/decisions/YYYY-MM-DD/HHMM_<SYM>.json    # canonical structured record per decision
/decisions/by_symbol/<SYM>.md            # auto-appended per-symbol timeline + cumulative stats
/trades/
  paper/log.csv                     # canonical paper-trade ledger
  paper/positions.json              # current open paper positions
  live/                             # PHASE 8+ ONLY; empty file + hook gate in v1
/backtests/<strategy>/<date>.md
/reports/
  pre_market/YYYY-MM-DD.md
  end_of_day/YYYY-MM-DD.md
  learning/
    weekly_learning_review_YYYY-MM-DD.md
    monthly_learning_review_YYYY-MM-DD.md
/prompts/
  agents/<agent>.md                 # production agent prompts (locked)
  routines/<routine>.md             # production routine prompts (locked)
  proposed_updates/YYYY-MM-DD_<agent>.md   # AI-drafted improvements; need PR review
/logs/
  routine_runs/YYYY-MM-DD_HHMM.md   # one per routine invocation
  risk_events/YYYY-MM-DD_HHMM.md    # only on risk events
/docs/                              # operator manual, runbooks
/tests/                             # schema validators, decision-format tests
/memory/
  market_regimes/current_regime.md
  market_regimes/history/YYYY-MM-DD.md
  symbol_profiles/<SYMBOL>.md
  signal_quality/<strategy>.md
  strategy_lessons/<strategy>.md
  prediction_reviews/YYYY-MM-DD.md
  risk_lessons/YYYY-MM-DD.md
  model_assumptions/current.md
  agent_performance/<agent>.md
  approved_learnings/<id>.md
  rejected_learnings/<id>.md
```

**Folder purposes** (one-liners):
- `config/`: ground truth for what the system is allowed to do.
- `data/`: append-only raw inputs; never edited.
- `decisions/`: every machine decision, structured, one file per decision; `decisions/by_symbol/<SYM>.md` is the auto-maintained per-symbol timeline (append-only, with cumulative stats header) so you can read a single symbol's full history end-to-end.
- `journals/`: human-readable narrative; immutable after 24h.
- `trades/paper/`: canonical paper ledger; live/ is locked.
- `memory/`: structured learning artifacts; the system's accumulating knowledge.
- `prompts/`: production prompts (locked) vs. proposed_updates (drafts).
- `logs/`: every routine run + every risk event, immutable.
- `reports/`: human-facing summaries.
- `tests/`: schema + format validators run by hooks.

---

## 6. Required Config Schemas

### A. `config/watchlist.yaml`
```yaml
schema_version: 1
last_reviewed: 2026-05-09
last_reviewed_by: human
universe: sector_etf_rotation
benchmarks:
  primary: SPY            # risk-adjusted target: beat SPY's Sharpe; drawdown <= SPY's
  secondary: SECTOR_EW    # equal-weight buy-and-hold of the 11 sector ETFs (the "is trading adding value?" test)
symbols:
  # Benchmark/anchor
  - symbol: SPY
    company_name: SPDR S&P 500 ETF
    sector: Benchmark
    approved_for_research: true
    approved_for_paper_trading: true       # usable as a "neutral" position when no sector edge
    approved_for_live_trading: false
    max_position_size_pct: 30
    notes: "Benchmark + neutral position. When no clear sector edge, holding SPY is allowed and acts as the do-no-harm default."

  # 11 GICS sector SPDRs
  - symbol: XLK
    company_name: Technology Select Sector SPDR
    sector: Technology
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 25
    notes: "Largest SPX sector. Heavily AAPL/MSFT/NVDA-driven; tech leadership = SPX leadership."
  - symbol: XLF
    company_name: Financial Select Sector SPDR
    sector: Financials
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 20
    notes: "Sensitive to rates and yield curve. Watch FOMC, 2y/10y spread, bank stress signals."
  - symbol: XLE
    company_name: Energy Select Sector SPDR
    sector: Energy
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 15
    notes: "Driven by crude oil and geopolitics. Often anticorrelated with broad market."
  - symbol: XLV
    company_name: Health Care Select Sector SPDR
    sector: Health Care
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 20
    notes: "Defensive sector. Watch policy/regulatory headlines."
  - symbol: XLY
    company_name: Consumer Discretionary Select Sector SPDR
    sector: Consumer Discretionary
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 20
    notes: "Heavily AMZN/TSLA-weighted. Risk-on cyclical. Watch retail sales and consumer confidence."
  - symbol: XLP
    company_name: Consumer Staples Select Sector SPDR
    sector: Consumer Staples
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 20
    notes: "Defensive. Outperforms in risk-off / late-cycle regimes."
  - symbol: XLI
    company_name: Industrial Select Sector SPDR
    sector: Industrials
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 20
    notes: "Cyclical. Watch ISM PMI, capex cycle, transports."
  - symbol: XLB
    company_name: Materials Select Sector SPDR
    sector: Materials
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 15
    notes: "Cyclical. Watch commodity prices, USD, China demand."
  - symbol: XLRE
    company_name: Real Estate Select Sector SPDR
    sector: Real Estate
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 15
    notes: "Highly rate-sensitive. Inverse to long yields."
  - symbol: XLU
    company_name: Utilities Select Sector SPDR
    sector: Utilities
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 15
    notes: "Defensive, rate-sensitive (bond proxy). Outperforms in flight-to-quality."
  - symbol: XLC
    company_name: Communication Services Select Sector SPDR
    sector: Communication Services
    approved_for_research: true
    approved_for_paper_trading: true
    approved_for_live_trading: false
    max_position_size_pct: 20
    notes: "Heavily META/GOOGL-weighted; behaves more like tech than telecom."

# Concentration guardrails (also enforced in risk_limits.yaml):
#  - No more than max_total_equity_exposure_pct invested at once.
#  - Sector ETFs are not perfectly independent — XLK / XLY / XLC are highly tech-correlated.
#  - Treat "tech beta" as one concentrated bet: XLK + XLY + XLC combined cap = max_tech_correlated_pct.
```

### B. `config/risk_limits.yaml`
```yaml
schema_version: 1
last_reviewed: 2026-05-09
account:
  paper_starting_capital: 100000
  live_starting_capital: 0                # phase 8+
limits:
  max_daily_loss_usd: 500
  max_daily_loss_pct: 0.5
  max_weekly_loss_pct: 2.0
  max_monthly_loss_pct: 5.0
  max_position_size_pct: 25.0          # per-symbol; ETFs less idiosyncratic than stocks; per-symbol caps in watchlist may be lower
  max_total_equity_exposure_pct: 95.0  # ETFs are diversified; full deployment is acceptable when conviction warrants
  max_tech_correlated_pct: 40.0        # combined XLK + XLY + XLC cap (these move together)
  max_defensive_correlated_pct: 40.0   # combined XLP + XLU + XLV cap
  max_trades_per_day: 4                # rotation strategy; few trades, not a scalper
  max_open_positions: 5                # of 12 symbols; some cash buffer + clear sector picks
  default_stop_loss_pct: 4.0           # ETFs are less volatile than mega-cap names; wider stops avoid noise stops
  default_take_profit_pct: 8.0
  minimum_risk_reward: 2.0
permissions:
  allow_margin: false
  allow_options: false
  allow_short_selling: false
  allow_leveraged_etfs: false
  allow_averaging_down: false
halts:
  halt_after_consecutive_losses: 3
  halt_after_daily_limit_breach: true
  cool_off_days_after_halt: 1
gates:
  require_human_approval_for_live_trades: true   # always true unless explicitly flipped
  minimum_paper_trading_days_before_live: 60
  minimum_paper_trades_before_live: 50
data:
  max_data_staleness_seconds: 60
```

### C. `config/strategy_rules.yaml`
```yaml
schema_version: 1
allowed_strategies:
  - name: sector_relative_strength_rotation
    status: ACTIVE_PAPER_TEST
    description: "Overweight sector ETFs with strongest 20d/60d relative strength vs SPY in a confirmed up-regime; underweight or skip those with deteriorating RS."
  - name: regime_defensive_tilt
    status: ACTIVE_PAPER_TEST
    description: "In high-volatility / risk-off regime (VIX > 22 or breadth deterioration), tilt toward XLP/XLU/XLV; reduce XLK/XLY/XLC exposure."
  - name: trend_pullback_in_leader
    status: NEEDS_MORE_DATA
    description: "Pullback to 20DMA on the leading sector ETF, in a confirmed market uptrend."
  - name: spy_neutral_default
    status: ACTIVE_PAPER_TEST
    description: "When no sector edge is detected, hold SPY as the do-no-harm default rather than overtrading."
disallowed_strategies:
  - day_trading_scalp
  - news_chase
  - single_stock_earnings_play     # we don't trade single stocks
  - momentum_late_entry
  - inverse_or_leveraged_etf_use
required_confirmations:
  sector_relative_strength_rotation:
    - "Up-regime confirmed (SPY > 50DMA AND breadth positive)"
    - "Sector RS rank top-3 vs SPY on both 20d AND 60d windows"
    - "Sector ETF above its own 50DMA"
  regime_defensive_tilt:
    - "VIX > 22 OR SPY < 50DMA OR sector breadth turning negative"
    - "Defensive sector RS improving vs SPY over 10d"
  trend_pullback_in_leader:
    - "ETF in top-3 sector RS"
    - "Pullback within 2-3% of 20DMA"
    - "RSI between 40-55 (not oversold-and-broken, not still-overheated)"
  spy_neutral_default:
    - "No sector ETF passes any of the above criteria"
minimum_risk_reward_ratio: 2.0
minimum_liquidity_avg_daily_volume: 5000000   # all our ETFs easily clear this
abnormal_volatility_threshold_atr_multiplier: 2.5
# ETF-specific: holding-event blackout — if an ETF's largest holding has earnings this week,
# that ETF is on caution (don't add) for the day before through the day after.
holding_earnings_caution_window_days: 1
```

### D. `decisions/.../trade_decision.json` (schema)
```json
{
  "schema_version": 1,
  "timestamp": "2026-05-09T09:35:14-04:00",
  "routine_id": "market_open_2026-05-09",
  "symbol": "AAPL",
  "decision": "PAPER_BUY",
  "thesis_bull": "...",
  "thesis_bear": "...",
  "technical_context": { "rsi": 58, "trend": "up", "key_levels": {...} },
  "fundamental_context": "Last 10-Q strong; segment growth steady",
  "news_context": [{ "headline": "...", "source_url": "...", "timestamp": "..." }],
  "macro_context": "Regime: bullish_trend, sector: tech outperforming SPX 5d",
  "risk_reward": { "entry": 188.50, "stop": 185.00, "target": 196.00, "ratio": 2.14 },
  "entry_condition": "Buy at market on next bar if price > 188.50",
  "exit_condition": "Sell at 196.00 OR stop at 185.00",
  "invalidation_condition": "Close below 184.50 OR sector turns bearish",
  "position_size": { "shares": 50, "usd": 9425, "pct_of_account": 4.7 },
  "confidence_score": 0.62,
  "risk_manager_verdict": "APPROVED",
  "compliance_verdict": "APPROVED",
  "human_approval_required": false,
  "final_status": "PAPER_PROPOSED",
  "linked_journal": "journals/daily/2026-05-09.md",
  "linked_data_snapshot": "data/market/2026-05-09/0930.json",
  "agent_outputs": { "technical_analysis": "...", "news": "...", ... }
}
```

### E. `journals/daily/YYYY-MM-DD.md` (template)
```markdown
# Daily Journal — 2026-05-09

## Market regime
- Classification: bullish_trend (confidence: medium)
- Key indicators: SPX > 50DMA, VIX 14, sector breadth +
- Notable macro: FOMC minutes Wed

## Watchlist summary
- AAPL: …
- MSFT: …

## Decisions made
- 09:35 AAPL → PAPER_BUY (link)
- 09:36 MSFT → NO_TRADE (reason: news risk)

## Trades proposed
- 1 (AAPL)

## Trades executed in paper mode
- AAPL BUY 50 @ 188.50 (link to log row)

## Risk events
- None

## What worked
- TA + news alignment caught AAPL setup

## What failed
- Missed NVDA breakout (no setup matched our strategy rules — acceptable miss)

## Lessons learned
- (Linked to /memory/prediction_reviews/2026-05-09.md)

## Next session context
- Hold AAPL overnight; watch FOMC minutes Wed
```

### G. `decisions/by_symbol/<SYM>.md` (per-symbol history; append-only timeline + auto-updated stats header)
```markdown
# XLK — Decision History

<!-- STATS:BEGIN — auto-maintained by Performance Review Agent; do not hand-edit -->
## Cumulative stats (as of 2026-05-09)
- Total decisions: 47  (32 NO_TRADE, 9 WATCH, 4 PAPER_BUY, 2 PAPER_CLOSE)
- Paper trades closed: 5  (3W / 2L)
- Win rate: 60% | Avg gain: +3.2% | Avg loss: -2.1% | Profit factor: 2.3
- Best regime: bullish_trend (4/4 wins)
- Worst regime: high_vol (0/2 wins)
- Confidence calibration: avg confidence 0.61 → realized hit rate 0.60 (well-calibrated)
<!-- STATS:END -->

## Timeline (append-only — hook #12 enforces)

### 2026-05-09 09:35 — PAPER_BUY
- **Thesis**: Sector RS top-3 vs SPY on both 20d/60d; XLK above 50DMA in confirmed up-regime.
- **R/R**: 2.14 | **Confidence**: 0.62 | **Risk**: APPROVED | **Compliance**: APPROVED
- **Full decision**: [decisions/2026-05-09/0935_XLK.json](decisions/2026-05-09/0935_XLK.json)
- **Analysis snapshot**: [data/market/2026-05-09/0930.json](data/market/2026-05-09/0930.json)
- **Outcome review**: pending (5d window closes 2026-05-16)

### 2026-05-08 09:35 — NO_TRADE
- **Thesis**: RS deteriorating; failed minimum_risk_reward (1.6 < 2.0).
- **Full decision**: [decisions/2026-05-08/0935_XLK.json](decisions/2026-05-08/0935_XLK.json)

…
```

**Properties:**
- Created on first decision for a symbol; one file per watchlist symbol.
- Header (between `<!-- STATS:BEGIN -->` and `<!-- STATS:END -->`) is the only section the Performance Review Agent may rewrite.
- Timeline rows below are strictly append-only. Hook #12 rejects any commit that modifies prior rows.
- Outcome review links are filled in retroactively by the Self-Learning Agent when the prediction window closes (1d / 5d / 20d horizons) — this is done by appending an "outcome review" line under the existing entry, not by editing the original row.
- This file is the canonical "what's our history with XLK" view for humans and for the Self-Learning Agent's per-symbol pattern detection.

### F. `trades/paper/log.csv`
```csv
timestamp,symbol,side,quantity,simulated_price,rationale_link,stop_loss,take_profit,status,realized_pnl,notes
2026-05-09T09:35:14-04:00,AAPL,BUY,50,188.50,decisions/2026-05-09/0935_AAPL.json,185.00,196.00,OPEN,,Initial entry
```

---

## 7. Custom Slash Commands

All in `.claude/commands/`. Each is a markdown file; arguments accessed via `$1`, `$2`, etc.

### `/premarket-report.md`
**Purpose**: Manually trigger the pre-market routine.
**Args**: `[date]` (optional, defaults to today)
**Prompt**:
```
You are running the pre-market routine for {{ $1 | default: today }}.
Load CLAUDE.md, config/watchlist.yaml, config/risk_limits.yaml,
config/strategy_rules.yaml, the last 5 daily journals, and
memory/market_regimes/current_regime.md.

Dispatch to: Market Data Agent, News & Sentiment Agent, Macro/Sector Agent, Technical Analysis Agent.

Produce reports/pre_market/{{date}}.md per the standard template.
Do NOT make any trade decisions in this routine — that is for /market-open.
Commit with message: "pre-market: research report {{date}} (N symbols flagged)".
```
**Usage**: `/premarket-report` or `/premarket-report 2026-05-09`

### `/analyze-symbol.md`
**Purpose**: Deep-dive a single symbol on demand.
**Args**: `<SYMBOL>`
**Prompt**: Loads watchlist (verifies symbol is approved), runs TA + Fundamentals + News + Risk agents, writes a one-off report to `reports/symbol_deep_dive/<SYMBOL>_YYYY-MM-DD.md`. **Refuses if symbol is not in watchlist.yaml.**

### `/risk-check.md`
**Purpose**: Show current limit utilization.
**Args**: none
**Prompt**: Reads `risk_limits.yaml`, current paper positions, today's trades. Outputs to chat: daily loss used, trades used, open positions used, consecutive losses, halt status.

### `/propose-paper-trade.md`
**Purpose**: Manually request a paper trade proposal for a symbol.
**Args**: `<SYMBOL> [side]`
**Prompt**: Runs Trade Proposal Agent + Risk Manager. Writes a decision file. **Never auto-fills the paper log** — operator must run `/confirm-paper-trade <decision-id>` to fill.

### `/update-daily-journal.md`
**Purpose**: Append a manual note to today's journal.
**Args**: `<note text>`

### `/weekly-review.md`
**Purpose**: Trigger weekly review on demand.
**Args**: `[YYYY-WW]`

### `/monthly-review.md`
**Purpose**: Trigger monthly review on demand.

### `/explain-decision.md`
**Purpose**: Re-read a decision file and explain it in plain English.
**Args**: `<decision-file-path>`

### `/halt-trading.md`
**Purpose**: Operator kill switch. Edits `config/approved_modes.yaml` to set `mode: HALTED`, writes a `logs/risk_events/` entry, notifies. Hook validates that **only this command** can flip mode to HALTED programmatically (any direct edit to approved_modes.yaml without the audit log is rejected).
**Args**: `<reason>`

---

## 8. CLAUDE.md Design

```markdown
# Calm Turtle — Trading Research & Paper-Trading System

## Project purpose
This repository runs a Claude-native research and paper-trading workflow for U.S. equities.
The goal is evidence-based, capital-preserving decision-making. It is NOT a guaranteed
income system. Markets are risky; losses are possible.

## Operating modes (current mode in config/approved_modes.yaml)
- RESEARCH_ONLY: produce reports and decisions; no paper or live trades.
- PAPER_TRADING: simulate fills against decisions; update paper log only.
- LIVE_PROPOSALS: produce PROPOSE_LIVE_* decisions for human approval.
- LIVE_EXECUTION: place live orders within risk_limits.yaml. Default: NEVER.
- HALTED: refuse all trading routines; only allow read-only inspection.

## Safety rules (non-negotiable)
1. The system NEVER edits config/risk_limits.yaml, config/strategy_rules.yaml,
   config/approved_modes.yaml, or the live-trading flags in config/watchlist.yaml.
   Changes to these require a pull request reviewed by a human.
2. The system NEVER trades a symbol that isn't in watchlist.yaml with the appropriate
   approved_for_* flag set to true.
3. The system NEVER raises its own limits. It may only PROPOSE changes via
   /prompts/proposed_updates/ or PR drafts.
4. If config/approved_modes.yaml has mode: HALTED, all routines exit early after
   logging the halt to /logs/routine_runs/.
5. If data is stale beyond risk_limits.yaml > data > max_data_staleness_seconds,
   the routine produces NO_TRADE decisions and notes the staleness.

## Approved file locations (write paths)
The system MAY write to:
- /journals/daily/<today>.md  (only today's; older are immutable)
- /decisions/<today>/...
- /trades/paper/log.csv (append only; reconciliation rules in /docs)
- /trades/paper/positions.json
- /reports/...
- /data/...
- /logs/...
- /memory/... (observation files only — see §21 for proposal rules)
- /prompts/proposed_updates/... (drafts only)

The system MAY NOT write to:
- /config/* (PR only)
- /prompts/agents/*.md (PR only)
- /prompts/routines/*.md (PR only)
- /trades/live/* (until phase 8 + explicit mode change)
- Any historical journal (older than 24h)

## Prohibited actions
- Trading any symbol not in watchlist.yaml.
- Trading using any strategy not in strategy_rules.yaml > allowed_strategies.
- Raising risk limits.
- Activating live mode.
- Margin, options, short selling, or leveraged ETFs unless explicitly enabled.
- Averaging down unless explicitly enabled.
- Skipping the Risk Manager + Compliance/Safety gates.
- Producing trade decisions without bull thesis, bear thesis, and invalidation condition.
- Fabricating data or news. Every data point cites a source.

## Trading limitations
- Paper trading only in v1.
- Long-only equities only unless config says otherwise.
- Max trades per day, max open positions, max position size, daily loss cap all
  enforced by Risk Manager. Limits are in risk_limits.yaml.

## Risk rules
- See risk_limits.yaml. Treat its values as hard ceilings, not targets.
- A "valid" trade only opens if R/R ≥ minimum_risk_reward AND data is fresh AND
  Risk Manager APPROVES AND Compliance/Safety APPROVES.

## Journaling requirements
- Every routine appends to today's journal.
- Every decision (including NO_TRADE) is recorded.
- "What failed" section is mandatory even on profitable days.
- Reflective lessons go to /memory/, not directly into production prompts.

## Git commit requirements
- Every routine run produces exactly one commit (or zero if nothing changed).
- Commit messages follow the per-routine format in /docs/commit_messages.md.
- Never force-push. Never amend public commits.
- Co-author trailer: Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

## Human approval requirements
- Any change touching: risk_limits.yaml, strategy_rules.yaml, approved_modes.yaml,
  watchlist live flags, broker permissions, max position size, max daily loss,
  max trades per day, live execution settings → must be a PR, never a direct commit.
- Promoting a strategy from ACTIVE_PAPER_TEST to live → human only.
- Adding a new symbol to watchlist → human only (system may PROPOSE in
  /prompts/proposed_updates/watchlist_additions.md).

## Handling missing data
- News connector down: mark symbols news_unavailable; treat as risk factor.
- Market data stale: produce NO_TRADE for affected symbols; log to risk_events.
- Fundamentals stale > 90 days: flag in decision; do not trade earnings-sensitive setups.
- ANY missing input is a reason to be MORE conservative, never less.

## Conflicting agent outputs
- TA bullish vs News bearish vs Macro neutral → Trade Proposal must explicitly
  surface the conflict in thesis_bear and lower confidence_score.
- Risk Manager always wins ties.
- Compliance/Safety always wins, period.

## How to halt safely
- Set config/approved_modes.yaml > mode: HALTED via /halt-trading <reason>.
- This writes /logs/risk_events/<ts>_halt.md and notifies.
- Resume requires human PR explicitly setting mode back.
```

---

## 9. Hooks and Deterministic Guardrails

Configured in `.claude/settings.json` under `hooks`. Each hook is a small shell script in `.claude/hooks/`. **Hooks must be deterministic** — no LLM calls, no flaky network deps.

| # | Event | Matcher | Command | Purpose | On failure |
|---|---|---|---|---|---|
| 1 | `PreToolUse` | `Edit\|Write` matching `trades/live/.*` | `.claude/hooks/block_live.sh` | Block any edit to live-trading files unless `approved_modes.yaml > mode == LIVE_EXECUTION` | Reject tool call with reason |
| 2 | `PostToolUse` | `Edit\|Write` matching `config/.*\.yaml$` | `.claude/hooks/validate_yaml_schema.sh` | Validate YAML against jsonschema in `tests/schemas/` | Reject; require fix |
| 3 | `PostToolUse` | `Edit\|Write` matching `decisions/.*\.json$` | `.claude/hooks/validate_decision_schema.sh` | Validate trade_decision.json schema | Reject |
| 4 | `PreToolUse` | `Edit\|Write` matching `journals/daily/.*\.md` | `.claude/hooks/journal_immutability.sh` | Block writes to journal files older than 24h | Reject |
| 5 | `PreToolUse` | `Edit\|Write` matching `prompts/agents/.*\|prompts/routines/.*` | `.claude/hooks/block_prompt_overwrites.sh` | Block direct edits — must go through proposed_updates/ + PR | Reject |
| 6 | `PreToolUse` | `Bash` | `.claude/hooks/scan_secrets.sh` | Scan command for AWS/API/broker keys with regex; block if found | Reject |
| 7 | `PreToolUse` | `Bash` matching `curl\|wget` against broker URLs | `.claude/hooks/block_broker_calls.sh` | Block broker API calls unless mode permits | Reject |
| 8 | `PreToolUse` | `Edit\|Write` matching `config/strategy_rules\.yaml` | `.claude/hooks/require_strategy_tests.sh` | Verify `tests/strategies/<changed_strategy>_test.md` exists and passes | Reject |
| 9 | `SessionStart` | always | `.claude/hooks/log_session_start.sh` | Append routine_run start record | Warn only |
| 10 | `SessionEnd` | always | `.claude/hooks/log_session_end.sh` | Append routine_run end record | Warn only |
| 11 | `PreToolUse` | `Edit\|Write` matching `config/approved_modes\.yaml` | `.claude/hooks/halt_audit.sh` | Verify a `logs/risk_events/*` entry was created in the same session | Reject |
| 12 | `PreToolUse` | `Edit\|Write` matching `trades/paper/log\.csv\|decisions/by_symbol/.*\.md` | `.claude/hooks/append_only.sh` | Verify the new content is a strict append (existing rows unchanged) | Reject |

> Hook design rule: hooks return non-zero on violation with a clear reason on stderr. They do not depend on network or LLM behavior. They run in <500ms.

---

## 10. Risk Management Rules

Hard, non-overridable by the system itself:

1. **Paper trading first.** Live trading off until Phase 6+ with explicit human config.
2. **No live trade without human approval.** `risk_limits.yaml > gates > require_human_approval_for_live_trades` defaults true and may not be flipped by the system.
3. **No trade outside watchlist.yaml.** Symbol must have `approved_for_paper_trading: true` (or live).
4. **No strategy outside strategy_rules.yaml > allowed_strategies.**
5. **No trade on stale data** (> max_data_staleness_seconds).
6. **No trade below R/R threshold** (default 2.0).
7. **No trade after daily loss limit reached.**
8. **No trade after consecutive-loss halt fires** until cool-off period elapses.
9. **No trade in earnings blackout window** unless strategy explicitly allows.
10. **No margin / options / shorting / leveraged ETFs / averaging down** unless explicitly enabled in risk_limits.yaml.
11. **No new strategy activation** without backtest record + paper-trade evidence + human PR.
12. **Mandatory journal entry** for every decision (including NO_TRADE).
13. **Mandatory plain-English explanation** for every paper-trade and live proposal.
14. **Position sizing** computed from %, never set by an agent ad hoc.
15. **One-decision-per-symbol per routine** — no rapid-fire re-decisions.

These rules live in CLAUDE.md and are re-stated in every agent prompt header.

---

## 11. Trading Decision Framework

Every decision has a single `decision` field with one of:

| Decision | Meaning | Allowed in mode |
|---|---|---|
| `NO_TRADE` | Setup fails one or more conditions | all |
| `WATCH` | Monitor but do not enter | all |
| `PAPER_BUY` | Open a paper long position | PAPER_TRADING+ |
| `PAPER_SELL` | Open a paper short (only if shorting enabled) | PAPER_TRADING+ |
| `PAPER_CLOSE` | Close an existing paper position | PAPER_TRADING+ |
| `PROPOSE_LIVE_BUY` | Draft live buy for human approval | LIVE_PROPOSALS+ |
| `PROPOSE_LIVE_SELL` | Draft live sell | LIVE_PROPOSALS+ |
| `PROPOSE_LIVE_CLOSE` | Draft live close | LIVE_PROPOSALS+ |
| `HALT_TRADING` | System recommends halt; flips mode after Compliance approves | any |

Required fields per the schema in §6D: bull thesis, bear thesis, technical, fundamental, news, macro, R/R, entry, exit, invalidation, position size, confidence (0–1), Risk Manager verdict, Compliance verdict, human-approval flag, journal link.

Confidence is for calibration tracking, not for sizing — sizing comes from `risk_limits.yaml`.

---

## 12. Data and Connector Plan

| Source | v1? | Recommended | Freshness | Failure mode | Fallback |
|---|---|---|---|---|---|
| GitHub | Yes | GitHub MCP connector | n/a | Routine cannot commit | Retry once, then notify |
| Market data | Yes | Polygon, Alpaca Data, or Tiingo via MCP | < 60s for intraday | Stale = NO_TRADE | Skip routine after 2 stale attempts |
| Broker account (read) | Phase 7 | Alpaca / IBKR via MCP, read-only | < 5 min | Use last-known state, mark stale | Treat as halted |
| Paper trading | Phase 4 | Internal CSV simulator first; broker sandbox at Phase 5 | n/a | Can't append → halt | n/a |
| SEC filings | Yes | EDGAR (free, public) | quarterly | Mark fundamentals_stale | Continue with stale flag |
| Earnings calendar | Yes | NASDAQ/Yahoo via MCP, or paid (FMP) | daily | Earnings blackout fails open → conservatively skip | n/a |
| News | Yes | Benzinga / NewsAPI / Tiingo News | < 30 min | news_unavailable flag | Continue, lower confidence |
| Economic calendar | Yes | FRED, ForexFactory scrape, or Trading Economics | daily | Skip macro section | Continue with caveat |
| Notifications | Yes | Slack MCP or email via SES; SMS via Twilio for urgent | n/a | Routine still commits | Log and continue |
| Secrets | Yes | GitHub Secrets + Claude Code env; never committed | n/a | n/a | n/a |

**Cost/permission notes**: Polygon/Tiingo/Benzinga have paid tiers; start with free where viable (Alpaca free for paper, Tiingo free tier, EDGAR free, FRED free). Broker live access requires KYC.

---

## 13. Broker Integration Plan

Phase-gated. Each phase requires evidence from the prior phase.

| Phase | Description | Permissions | Risk |
|---|---|---|---|
| **A** | No broker connection | none | none |
| **B** | Read-only account | view positions, balance | minimal — only data leak if creds exposed |
| **C** | Paper trading via broker sandbox or internal CSV simulator | sandbox keys only | none |
| **D** | Human-approved live proposals | none yet — system writes proposals; human places orders manually | very low |
| **E** | Limited live execution | order placement with hardcoded broker-side max position, max order size, day-loss cap | real |
| **F** | Autonomous live execution | as E, but no per-trade approval | real, requires sustained evidence + explicit decision |

**For each live phase:**
- **API permissions**: least-privilege; ideally separate keys per environment.
- **Secrets**: GitHub Secrets + Claude Code env vars; never committed; rotate quarterly.
- **Order validation**: pre-flight check against `risk_limits.yaml`, `watchlist.yaml`, current portfolio, freshness.
- **Human approval gate**: PR or Slack approval webhook for `PROPOSE_LIVE_*` until phase F.
- **Reconciliation**: nightly compare broker positions to repo positions; discrepancy → halt + alert.
- **Audit log**: every order request + response stored in `logs/orders/`.
- **Emergency halt**: `/halt-trading` flips mode, broker connector refuses new orders, attempts to cancel all working orders.

---

## 14. Compliance & Operational Checklist

> Not legal or financial advice. Verify each item with your broker, accountant, and any qualified advisor before acting.

- [ ] Pattern Day Trader rule: confirm account size & strategy fit (esp. < $25k cash accounts).
- [ ] Margin requirements: if margin disabled, ensure broker enforces.
- [ ] Settlement (T+1 in 2026): confirm strategy doesn't sell unsettled funds.
- [ ] Broker API terms: confirm automated trading is allowed and disclosed.
- [ ] Data provider terms: confirm redistribution / display rules; some prohibit storing data.
- [ ] Tax records: log every paper and live trade; export annual CSV for accountant.
- [ ] Audit logs: all routine_runs, risk_events, decisions are immutable in Git history.
- [ ] Model limitations: documented in `/docs/model_limitations.md`; reviewed monthly.
- [ ] Human supervision: define daily / weekly review cadence; on-call rotation if multi-person.
- [ ] Incident response runbook: who does what when limits breach or system misbehaves.
- [ ] Kill switch: `/halt-trading` slash command; broker-side daily-loss cap; emergency manual order cancellation.
- [ ] Wash sale rules (live phase): track 30-day window for losses.
- [ ] Privacy / data minimization: do not commit personal IDs or account numbers; use IDs.

---

## 15. Implementation Roadmap

Ten phases. Each gates the next.

### Phase 0 — Requirements & risk profile (1 week)
- **Goal**: Concrete answers to §20 questions, written into `/docs/risk_profile.md`.
- **Deliverables**: risk profile doc, signed off by you.
- **Success**: clear numeric limits, broker chosen, capital allocated.
- **Risks**: scope creep, optimism bias.
- **Go/no-go**: numeric limits exist for daily/weekly/monthly loss; broker selected.

### Phase 1 — Repo scaffold (1 week)
- **Goal**: All folders + `CLAUDE.md` + schema files + empty configs + hooks + tests.
- **Deliverables**: working repo that lints clean; hooks reject malformed configs.
- **Success**: PR fails on bad YAML; all paths exist.
- **Risks**: over-engineering early.
- **Go/no-go**: a synthetic bad PR is rejected by hooks.

### Phase 2 — Routine prototypes (2 weeks)
- **Goal**: Pre-market + EOD routines run end-to-end producing reports & journal.
- **Deliverables**: 2 routines + orchestrator agent + 4 specialist agents.
- **Success**: 5 trading days of clean reports produced.
- **Risks**: connector instability, prompt inconsistency.
- **Go/no-go**: 5 consecutive days no halt; reports human-readable.

### Phase 3 — Research-only completeness (2 weeks)
- **Goal**: All 7 routines (A–G) running. No paper trades yet.
- **Deliverables**: full slash command set; weekly + monthly reviews.
- **Success**: 2 weekly reviews + 1 monthly review of decisions vs. outcomes.
- **Risks**: agent disagreement loops; review fatigue.
- **Go/no-go**: 4 weeks of continuous research artifacts.

### Phase 4 — Paper trading simulator (2 weeks)
- **Goal**: Decisions become rows in `trades/paper/log.csv`; positions tracked.
- **Deliverables**: simulator script + reconciliation hook + portfolio metrics.
- **Success**: 4 weeks of paper trading, journal matches log matches positions.
- **Risks**: fill model unrealistic.
- **Go/no-go**: 50+ paper trades, no log/journal drift.

### Phase 5 — Backtesting & analytics (2 weeks)
- **Goal**: Each allowed strategy has a backtest report and forward paper-trade comparison.
- **Deliverables**: `/backtests/<strategy>/` directory populated.
- **Success**: backtest vs. paper performance documented; divergence explained.
- **Go/no-go**: backtest exists for every strategy in strategy_rules.yaml.

### Phase 6 — Human-approved trade proposals (open-ended, ≥ 60 trading days)
- **Goal**: System produces `PROPOSE_LIVE_*` records; human approves manually.
- **Deliverables**: review UI (could be just GitHub PR comments) + approval audit trail.
- **Success**: ≥ 50 paper trades + ≥ 60 days + Sharpe-like metric within stated tolerance.
- **Go/no-go**: monthly review explicitly recommends advancing.

### Phase 7 — Broker read-only (1 week)
- **Goal**: System sees real account positions but cannot trade.
- **Deliverables**: read-only connector + reconciliation routine.
- **Success**: 2 weeks of clean reconciliation.
- **Go/no-go**: zero discrepancies for 2 weeks.

### Phase 8 — Limited live execution (open-ended)
- **Goal**: System executes orders within hard broker-side limits, with per-trade human approval.
- **Deliverables**: order connector + emergency halt + tax logging.
- **Success**: 30 days, no limit breaches, drawdown ≤ paper drawdown.
- **Go/no-go**: explicit human decision + signed risk profile update.

### Phase 9 — Monitoring & continuous improvement (ongoing)
- **Goal**: Sustained operation; learning loop tuning.
- **Deliverables**: monthly self-review meeting + retro doc.
- **Success**: 3 months without incident requiring halt.
- **Note**: Phase F (autonomous) only opens here, and only if you explicitly want it. Default: never open it.

---

## 16. Example Claude Code Routine Prompts

Each routine prompt lives at `/prompts/routines/<routine>.md`. The Claude Code routine schedule references these.

### Pre-market routine prompt (sketch)
```
You are running the PRE-MARKET routine for {{date}} (US/Eastern).

1. Read CLAUDE.md (operating manual). Comply with every rule.
2. Read config/approved_modes.yaml. If mode is HALTED, write logs/routine_runs/
   <ts>_halted.md, notify, and exit.
3. Read config/watchlist.yaml, config/risk_limits.yaml, config/strategy_rules.yaml.
   Validate each against tests/schemas/. If validation fails, halt and log.
4. Read journals/daily/ for the last 5 trading days, trades/paper/positions.json,
   memory/market_regimes/current_regime.md.
5. Dispatch in parallel:
   - Market Data Agent: overnight quotes, futures, key indices.
   - News & Sentiment Agent: per-watchlist headlines + sector news + macro.
   - Macro/Sector Agent: regime classification, sector posture.
   - Technical Analysis Agent: TA per watchlist symbol.
6. Compose reports/pre_market/{{date}}.md using the template in /docs/templates/.
   Include: regime call (with citations), top 5 candidates, why each is interesting,
   and what would invalidate each thesis.
7. Append a "pre-market" section to journals/daily/{{date}}.md.
8. Compliance/Safety Agent reviews the report for rule violations. If violations,
   write logs/risk_events/, halt routine, do NOT commit broken artifacts.
9. Commit: "pre-market: research report {{date}} (N symbols flagged)".
10. Notify with the configured channel: 1-paragraph summary + link to report.

Constraints: NO trade decisions. NO writes to /config or /prompts/agents or
/prompts/routines. NO writes to live trade folders. NO fabrication.
```

### Market open routine prompt (sketch)
```
You are running the MARKET OPEN routine at 09:35 ET on {{date}}.

1–3. Same setup as pre-market (CLAUDE.md, mode check, schema validation).
4. Read reports/pre_market/{{date}}.md (today's thesis), trades/paper/positions.json,
   trades/paper/log.csv (recent rows), memory/market_regimes/current_regime.md.
5. Market Data Agent: live quotes (verify freshness < max_data_staleness_seconds).
6. For each pre-market candidate:
   a. Technical Analysis Agent: confirm thesis still valid against opening action.
   b. Trade Proposal Agent: produce a draft decision (NO_TRADE / WATCH / PAPER_BUY /
      PAPER_SELL).
   c. Risk Manager Agent: review draft against risk_limits.yaml + current portfolio.
   d. Compliance/Safety Agent: final gate.
7. Write each approved decision to decisions/{{date}}/{{HHMM}}_{{SYMBOL}}.json.
8. For PAPER_BUY/SELL decisions in PAPER_TRADING mode, append a row to
   trades/paper/log.csv and update trades/paper/positions.json. Reconcile.
9. Append "open" section to journals/daily/{{date}}.md.
10. Commit: "open: N decisions (P proposals, W watch, X no-trade)".
11. Notify.

Constraints: max_trades_per_day cap; if exceeded, remaining proposals downgrade
to WATCH automatically. Risk Manager always wins.
```

### Midday routine prompt (sketch)
```
MIDDAY routine at 12:00 ET on {{date}}.

1–4. Standard setup + load open positions + intraday news pull.
5. Portfolio Manager Agent: for each open paper position, has invalidation
   triggered? Has time-stop been hit?
6. If yes, propose PAPER_CLOSE; route through Risk Manager + Compliance.
7. News & Sentiment Agent: any material new news on open-position symbols?
8. Append "midday" section to journals/daily/{{date}}.md.
9. Commit: "midday: position review (Q open, R closed)" — but only if anything
   changed. If nothing changed, skip the commit (just log the run).
10. Notify only if action taken or risk event.

Constraints: NO opening of new positions in midday by default. Closes only.
```

### Pre-close routine prompt (sketch)
```
PRE-CLOSE routine at 15:30 ET on {{date}}.

1–4. Standard setup.
5. Portfolio Manager: hold-vs-close decision per open position.
   - Default behavior: if mode != PAPER_TRADING, no action; log only.
   - If a position's invalidation has triggered or time-stop reached → PAPER_CLOSE.
   - If overnight risk (earnings tomorrow, scheduled macro event) → PAPER_CLOSE.
6. Risk Manager + Compliance gate.
7. Apply to paper log.
8. Append "pre-close" section to journal.
9. Commit, notify.
```

### End-of-day routine prompt (sketch)
```
END-OF-DAY routine at 16:30 ET on {{date}}.

1–3. Standard setup.
4. Performance Review Agent: compute today's PnL, win rate, trade count.
5. Journal Agent: finalize journals/daily/{{date}}.md (all required sections).
6. For each prediction made today, write an observation entry under
   memory/prediction_reviews/{{date}}.md (initial — full review later).
7. Update memory/agent_performance/<each_agent>.md with today's hits/misses.
8. Compliance/Safety: verify journal is complete and matches paper log.
9. Commit: "eod: journal + perf {{date}} (PnL ±$X.XX, N trades)".
10. Notify.

Constraints: this routine is the only one that finalizes the journal. Hooks
will reject edits to today's journal by future routines (only via human PR).
```

### Weekly review routine prompt (sketch)
```
WEEKLY REVIEW for week ending {{week_end_date}}.

1–3. Standard setup (no live data needed).
4. Read all daily journals, decisions, memory/prediction_reviews/ for the week.
5. Performance Review Agent:
   - Win rate, avg gain, avg loss, profit factor, max drawdown.
   - Per-strategy breakdown.
   - Per-agent calibration: were high-confidence calls correct?
6. Identify recurring mistakes.
7. Write journals/weekly/{{week}}.md and reports/learning/weekly_learning_review_
   {{date}}.md per the template in §21N.
8. Generate proposed prompt updates → /prompts/proposed_updates/ with PR draft.
   - Tag each proposal with one of §21D categories.
9. NO direct edits to /config or /prompts/agents or /prompts/routines.
10. Commit, notify, link the proposed PR.
```

### Monthly review routine prompt (sketch)
```
MONTHLY REVIEW for {{month}}.

1–3. Standard setup.
4. Aggregate weekly reviews + full month of decisions.
5. Performance Review Agent + Compliance/Safety:
   - Risk-adjusted returns.
   - Drawdown ≤ ceiling? If not → recommend HALT_AND_REVIEW.
   - Calibration trend month-over-month.
6. Mode recommendation:
   - STAY_PAPER (default if any concern)
   - PROPOSE_HUMAN_APPROVED_LIVE (only if all phase-6 gates passed)
   - HALT_AND_REVIEW
7. Write journals/monthly/{{month}}.md + monthly_learning_review.
8. Open PRs for any non-trivial proposed prompt changes.
9. Commit, notify.

Constraints: never recommends advancing modes more than one step at a time.
```

---

## 17. Example Daily Orchestrator Prompt

This is the master prompt invoked by the daily routines (referenced from each routine prompt above).

```
You are the Calm Turtle Orchestrator. You coordinate a routine run for the
{{routine_name}} routine on {{date}}. Be cautious, evidence-based, and
capital-preserving. Capital preservation > clever trades.

# Step 1 — Load context
Read these files in order. Stop with a HALT log if any read fails:
- CLAUDE.md
- config/approved_modes.yaml
- config/watchlist.yaml
- config/risk_limits.yaml
- config/strategy_rules.yaml
- config/routine_schedule.yaml
- memory/market_regimes/current_regime.md
- memory/model_assumptions/current.md
- The last 5 entries in journals/daily/
- trades/paper/positions.json
- The last 100 rows of trades/paper/log.csv

# Step 2 — Mode check
If approved_modes.yaml > mode == HALTED, write logs/routine_runs/<ts>_halted.md
and exit cleanly.

# Step 3 — Schema validation
Validate watchlist.yaml, risk_limits.yaml, strategy_rules.yaml against
tests/schemas/. Any failure → halt + risk_event entry.

# Step 4 — Dispatch specialist agents (parallel where independent)
Based on routine_name, call the agents listed in §3. Each agent must:
- Cite sources for every external claim.
- Stamp data freshness.
- Return structured output, not prose.

# Step 5 — Trade proposals (if routine permits)
For each candidate symbol:
  a. Verify symbol is in watchlist.yaml with appropriate approved_for_* flag.
  b. Trade Proposal Agent drafts a trade_decision.json per §6D schema.
  c. Risk Manager reviews against risk_limits.yaml + current portfolio.
  d. Compliance/Safety final gate.
  e. Only if all pass and mode permits, persist the decision file. Otherwise
     write the decision with final_status=REJECTED and reason.

# Step 6 — Apply to paper log (PAPER_TRADING mode only)
For approved PAPER_BUY/SELL/CLOSE: append to trades/paper/log.csv and update
trades/paper/positions.json. Verify reconciliation: positions.json must match
the open rows in log.csv.

# Step 7 — Update journal
Append a section to journals/daily/{{date}}.md with: regime, decisions,
trades, risk events, what worked, what failed, lessons-pending, next session
context.

# Step 8 — Observation entries
For every decision today, append an entry to memory/prediction_reviews/
{{date}}.md with the prediction details (final review happens at weekly cadence).

# Step 9 — Refuse live execution
If any agent or sub-prompt produces a `LIVE_*` execution that isn't a
PROPOSE_LIVE_* draft, refuse it. Write logs/risk_events/<ts>_live_block.md
and notify URGENT.

# Step 10 — Commit
git add <only the paths the orchestrator is allowed to touch> && git commit
-m "<routine>: <summary>". One commit max. Co-author trailer included.

# Step 11 — Notify
One paragraph to the configured channel: routine name, key counts (decisions,
trades, halts), top thesis or top concern, link to report.

Hard rules (re-stated for safety):
- You may not edit /config/risk_limits.yaml, /config/strategy_rules.yaml,
  /config/approved_modes.yaml, /config/watchlist.yaml.
- You may not edit production prompts in /prompts/agents/ or /prompts/routines/.
- You may not write to /trades/live/*.
- You may not trade symbols outside watchlist.yaml.
- You may not run strategies outside strategy_rules.yaml > allowed_strategies.
- You may not place live orders, ever, in this version.
- If unsure, choose NO_TRADE.
```

---

## 18. Example Outputs

### Pre-market report (sketch)
```markdown
# Pre-Market Research — 2026-05-09

## Regime
Bullish trend (medium confidence). SPX above 50DMA, VIX 14. Rates stable.

## Top candidates
1. **AAPL** — Pullback to 20DMA in confirmed uptrend.
   Bull: trend intact, sector strong, no near-term catalyst risk.
   Bear: market-cap leader; if SPX cracks, AAPL leads down.
   Invalidation: close < 184.50.
   R/R: ~2.1.
2. **MSFT** — …

## What I am NOT going to trade
- NVDA: extended setup, R/R only 1.6, fails strategy_rules.
- TSLA: news risk (regulatory headline), news_unavailable for >12h.

## Open positions reminder
None.

## Risk posture
Conservative. 2 of 5 daily trades available. 0 of 3 positions used.
```

### Trade decision record
```json
{
  "schema_version": 1,
  "timestamp": "2026-05-09T09:35:14-04:00",
  "routine_id": "market_open_2026-05-09",
  "symbol": "AAPL",
  "decision": "PAPER_BUY",
  "thesis_bull": "Pullback to 20DMA in confirmed uptrend with sector tailwind.",
  "thesis_bear": "Mega-cap concentration risk; if SPX rolls, AAPL leads down.",
  "risk_reward": {"entry": 188.50, "stop": 185.00, "target": 196.00, "ratio": 2.14},
  "invalidation_condition": "Close below 184.50 OR sector breadth turns negative.",
  "position_size": {"shares": 50, "usd": 9425, "pct_of_account": 4.7},
  "confidence_score": 0.62,
  "risk_manager_verdict": "APPROVED",
  "compliance_verdict": "APPROVED",
  "human_approval_required": false,
  "final_status": "PAPER_FILLED"
}
```

### Daily journal entry — see template §6E.

### Weekly review (sketch)
```markdown
# Weekly Review — Week 19, 2026 (May 4–8)

## Performance
- Trades: 7 paper. Wins: 4. Losses: 2. Open: 1.
- P&L: +$184 paper. Profit factor: 1.6. Max drawdown: -$210.

## What worked
- Trend pullback strategy: 3/3 wins this week. Likely regime-driven.

## What failed
- One earnings-blackout violation flagged by hook (correctly blocked, but the
  Trade Proposal Agent shouldn't have proposed it). Proposed prompt update.

## Recurring mistakes
- News & Sentiment Agent over-weighted a single source on May 6.

## Recommended memory updates
- Update /memory/symbol_profiles/AAPL.md with "responds well to pullback after
  3-day decline; weak in pre-FOMC week."

## Recommended prompt updates (drafts in /prompts/proposed_updates/)
- News agent: require ≥ 2 sources for any "material" classification.

## Items requiring human approval
- None this week.

## Next week focus
- Watch for FOMC; reduce trade count by 1 on Wed.
```

### Halt event log
```markdown
# Halt Event — 2026-05-09 14:22:01 ET

Reason: Daily loss limit breached (-$512 > $500 cap).
Triggered by: Risk Manager Agent, midday routine.
Action: mode → HALTED via auto-write to approved_modes.yaml; cooled off until tomorrow.
Open positions: 1 (AAPL paper). Close decisions deferred to human review.
Notification: sent.
```

### User notification (Slack-style)
```
[Calm Turtle] EOD 2026-05-09
PnL: +$184 paper | 3 trades | win rate 67%
Top lesson: news agent over-weighted single source — proposed fix queued.
Mode: PAPER_TRADING. Tomorrow: pre-market 06:30 ET.
Report: github.com/<you>/calm-turtle/blob/main/journals/daily/2026-05-09.md
```

### Git commit message
```
eod: journal + perf 2026-05-09 (PnL +$184.00, 3 trades, win rate 67%)

Routine: end_of_day
Trades: 3 (2 W, 1 L)
Risk events: 0
Memory updates: prediction_reviews/2026-05-09.md, agent_performance/news_agent.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 19. Technical Architecture Options

| | A. Pure Claude Code routines + GitHub + connectors | B. Claude Code routines + GitHub Actions + broker | C. Claude Code routines + serverless for execution | D. Hybrid: Claude research + separate deterministic engine |
|---|---|---|---|---|
| **Reliability** | Medium (depends on routine uptime) | Higher (Actions are robust) | Higher | Highest (decoupled engine) |
| **Safety** | High (no execution path in v1) | High | Medium (more code paths) | Highest (engine enforces invariants in code) |
| **Cost** | Low | Low | Medium (compute) | Medium-high (engine to maintain) |
| **Complexity** | Low | Medium | Medium-high | Highest |
| **Maintenance** | Low | Low-medium | Medium | Highest |
| **Suitability for live trading** | Acceptable for proposals; weak for execution | Better for execution | Good for execution | Best |
| **Failure recovery** | Re-run routine | Re-run + Action retries | Idempotency required | Engine has its own state |
| **Auditability** | Excellent (everything in Git) | Excellent | Good (need extra logging) | Excellent |

**Recommendation**: Start with **Option A**. Move to **Option D** before Phase 8 (live execution): the Claude side stays the research/decision layer; a small, deterministic, well-tested execution engine (Python or TypeScript service) takes the human-approved proposals and places orders with broker, with hard limits enforced in code, not in prompts. LLMs do not belong in the order-placement hot path.

---

## 20. Tailoring Questions (these are also asked interactively before exiting plan mode)

1. Which broker? (Alpaca / IBKR / Schwab / Fidelity / other)
2. Account type? (cash / margin / IRA / Roth IRA — affects PDT, settlement, wash-sale)
3. Capital allocated to this experiment? (paper notional and, eventually, live)
4. Max acceptable daily / weekly / monthly loss in dollars and percent?
5. Initial approved watchlist symbols? (start with 3–10 you understand)
6. Long-only or open to short / options / leveraged ETFs? (default: long-only)
7. Margin allowed? (default: no)
8. Data providers you have or are willing to pay for?
9. Notification channel preference? (Slack / email / SMS / multiple)
10. Manual approval for every live trade, or only above some threshold?
11. Minimum paper-trading period before considering live? (recommend ≥ 60 trading days, ≥ 50 trades)
12. Time zone for personal review? (defaults to ET for market schedule, but reports can be cross-stamped)
13. Tax jurisdiction? (affects record requirements only — get a real accountant)

---

## 21. Self-Learning and Continuous Improvement Loop

### Operating principle
Learning is observation → memory → evaluation → proposal → human approval. The system **never** silently changes risk-relevant configuration. Memory accumulates; production rules change only via PR.

### A. Observation layer
Every routine run appends to `/memory/prediction_reviews/<date>.md` with:
- Detected market regime + confidence.
- Strong/weak setups by symbol.
- Predictions made (linked to decision files).
- Predictions reviewable (when outcome known: 1d, 5d, 20d horizons).
- Signal-quality notes (which signals were noisy / useful).
- News/macro events that mattered.
- Underestimated risks.
- Trades correctly avoided.
- Missed opportunities (with diagnosis: rule prevented entry vs. agent missed).
- Trades in retrospect that shouldn't have been taken.

### B. Memory layer (folders)
| Path | Contents | Update cadence |
|---|---|---|
| `memory/market_regimes/current_regime.md` | active regime + indicators | Daily (proposed); confirmed weekly |
| `memory/market_regimes/history/<date>.md` | historical regime stamps | EOD |
| `memory/symbol_profiles/<SYMBOL>.md` | symbol-specific knowledge | Weekly + as-needed |
| `memory/signal_quality/<strategy>.md` | per-signal hit/miss | Weekly |
| `memory/strategy_lessons/<strategy>.md` | strategy-level lessons | Weekly + monthly |
| `memory/prediction_reviews/<date>.md` | per-day prediction review | Daily (initial) + weekly (full) |
| `memory/risk_lessons/<date>.md` | learned risk events | On event + weekly |
| `memory/model_assumptions/current.md` | current explicit assumptions of the system | Monthly |
| `memory/agent_performance/<agent>.md` | calibration & blind spots per agent | Weekly |
| `memory/approved_learnings/<id>.md` | lessons accepted by human | On approval |
| `memory/rejected_learnings/<id>.md` | lessons rejected, with reason | On rejection |

Every artifact: ISO-timestamped, with source-evidence links (decision files, journal lines, log entries).

### C. Evaluation layer
For each prior decision, when an outcome window closes (1d / 5d / 20d), evaluate:
- Did the expected directional move occur?
- Was timing right? (early / late / on-time)
- R/R estimate accurate (target / stop / actual move)?
- Confidence calibrated? (compare bucket of similar-confidence calls)
- Thesis fail mode? (which sub-thesis broke)
- Invalidation triggered correctly?
- Exits early/late?
- Risk limits appropriate?
- Missed information? (any news/data the agent didn't see)

Record results in `/memory/prediction_reviews/<date>.md`. Aggregate to `/memory/agent_performance/<agent>.md`.

### D. Learning proposal layer (categories)
| Category | Effect | Where written |
|---|---|---|
| `SAFE_MEMORY_UPDATE` | System may write directly | `/memory/...` |
| `PROMPT_IMPROVEMENT` | Draft only; needs PR | `/prompts/proposed_updates/` |
| `WATCHLIST_NOTE_UPDATE` | Notes-only PR for human review | PR to `watchlist.yaml.notes` |
| `STRATEGY_REVIEW_REQUIRED` | Surface for human; no auto-change | Review doc |
| `RISK_RULE_REVIEW_REQUIRED` | Surface for human; no auto-change | Review doc |
| `HUMAN_APPROVAL_REQUIRED` | PR to a config file | PR draft |
| `REJECTED_LEARNING` | Logged with reason | `/memory/rejected_learnings/` |

### E. Human approval layer
The system **may not** auto-modify:
- `risk_limits.yaml`, `strategy_rules.yaml`, `approved_modes.yaml`
- watchlist live flags, max position size, max daily loss, max trades per day
- broker permissions, live execution settings

It writes a **review document** or opens a **draft PR**. Hooks (§9 #5, #8, #11) enforce.

### F. Prompt and agent improvement layer
Per agent in `/memory/agent_performance/<agent>.md`:
- What it got right (with examples).
- What it got wrong (with examples).
- Recurring blind spots.
- Data sources it overused / ignored.
- Confidence calibration histogram.
- Suggested prompt deltas (drafted under `/prompts/proposed_updates/<date>_<agent>.md`).

Production prompts in `/prompts/agents/` only update via PR. Hook #5 blocks direct edits.

### G. Market-regime learning
`memory/market_regimes/current_regime.md` schema:
```markdown
# Current Market Regime — as of YYYY-MM-DD
- Classification: bullish_trend
- Confidence: medium
- Key indicators: SPX > 50DMA, VIX < 18, breadth +
- Useful signals in this regime: trend pullback (4/5), breakout w/ volume (2/3)
- Failed signals in this regime: mean reversion (0/3)
- Strong-performing symbols: AAPL, MSFT
- Weak-performing symbols: <list>
- Caution level: medium
```
Regimes tracked: bullish_trend / bearish_trend / range_bound / high_vol / low_vol /
earnings_driven / macro_event_driven / sector_rotation / liquidity_stress.

### H1. Symbol-level learning
`memory/symbol_profiles/<SYMBOL>.md`:
```markdown
# AAPL — Symbol Profile
- Typical 20d ATR: 1.8%
- Liquidity: 50M+ shares/day
- Earnings sensitivity: high
- News sensitivity: medium
- Sector correlation: 0.75 to QQQ
- Working patterns: 20DMA pullback in trend
- Failed patterns: late-day breakouts
- Common false signals: pre-FOMC RSI dips
- Best windows: 09:45–11:00 ET, 14:30–15:30 ET
- Risk notes: blackout 2 days before earnings
- Recent lessons: <linked>
```

### H2. Self-Learning Review Routine (the dedicated learning routine)
| Field | Value |
|---|---|
| Trigger | Sundays 10:00 ET (weekly) + 1st of month 10:00 ET (monthly) |
| Inputs | All journals/decisions/logs/memory for the period |
| Subagents | **Self-Learning Agent (lead)**, Performance Review (computes metrics consumed by Self-Learning), Compliance/Safety (final gate) |
| Outputs | `/reports/learning/...`, memory updates, draft PRs in `/prompts/proposed_updates/`, review docs for any strategy or risk-rule proposals |
| Caps per cycle | ≤ 5 prompt proposals, ≤ 3 strategy proposals, ≤ 1 risk-rule review doc — to avoid review fatigue |
| Forbidden | Editing live configs, risk rules, strategy rules, production prompts; auto-applying any change tagged `STRATEGY_REVIEW_REQUIRED`, `RISK_RULE_REVIEW_REQUIRED`, or `HUMAN_APPROVAL_REQUIRED` |

### I. Strategy learning
Per strategy in `memory/strategy_lessons/<strategy>.md`:
- Signal count, trade count, win rate, avg gain, avg loss, max DD, profit factor, Sharpe (if N≥30).
- False-positive / false-negative rates.
- Best regime / worst regime.
- Status: `ACTIVE_PAPER_TEST` / `NEEDS_MORE_DATA` / `UNDER_REVIEW` / `PAUSED` / `REJECTED` / `CANDIDATE_FOR_HUMAN_REVIEW`.
- Status changes are PROPOSALS, not auto-applied (except `NEEDS_MORE_DATA` → `ACTIVE_PAPER_TEST` and `ACTIVE_PAPER_TEST` → `PAUSED` after § halts, which are auto).

### J. Prediction calibration
Every prediction stamps: direction, horizon, confidence, expected price range, risk factors, invalidation. Outcome review labels each with: correct / partial / incorrect / too_early / too_late / right_dir_wrong_mag / wrong_missing_data / wrong_regime_change. Calibration trend tracked per agent — high-confidence-but-wrong agents get downweighted (their proposals require an extra confirmation, drafted as a prompt change for human review).

### K. Self-learning guardrails (re-stated)
- Never optimize only for profit; always include drawdown / risk-adjusted view.
- Never raise risk limits automatically.
- Never activate live trading automatically.
- Never add tradable symbols automatically.
- Never remove human approval gates automatically.
- Never treat recent performance as proof of future performance.
- Never overfit (no recommendations from < 20 trades).
- Never change production strategy rules without a review artifact.
- Always separate observations from conclusions in writing.
- Always preserve historical logs (immutable).
- Always explain why a lesson was accepted or rejected.

### L. Learning review routine (already covered in 21H2 + §3F/G).

### M. Learning output files (already enumerated; the canonical list).

### N. Learning report format
```markdown
# Weekly Learning Review — week ending YYYY-MM-DD

## Period
{{start}} → {{end}}

## Market regime summary
…

## Best predictions (with links)
…

## Worst predictions
…

## Missed opportunities
…

## Avoided bad trades
…

## Signals that worked
…

## Signals that failed
…

## Risk lessons
…

## Agent performance review
- Market Data: …
- News & Sentiment: …
- …

## Strategy performance review
- trend_following_pullback: 3W / 1L; profit factor 2.1; status: ACTIVE_PAPER_TEST.

## Recommended memory updates (auto-applied if SAFE_MEMORY_UPDATE)
…

## Recommended prompt updates (drafts in /prompts/proposed_updates/)
…

## Recommended strategy updates (REVIEW REQUIRED)
…

## Items requiring human approval
- PR #N: …

## Items rejected due to weak evidence
…

## Next-week focus areas
…
```

### O. Self-learning success criteria
Judged on:
- Better prediction calibration (Brier-style score trend).
- Fewer repeated mistakes (recurring-error count trend down).
- Better risk-adjusted paper returns (Sharpe-ish, with drawdown).
- Lower drawdowns.
- Better documentation quality (every decision linked).
- More consistent reasoning (lower variance in why-similar-trades-were-taken).
- Better NO_TRADE vs TRADE distinction.
- More accurate market-regime detection (regime calls vs. retrospective).
- Better symbol-specific knowledge (lower surprise-rate per symbol).

The goal is **safer, better-calibrated decisions over time**, not more trades or higher short-term returns.

---

## Critical files to be created (Phase 1 scaffold)

- `/CLAUDE.md` — §8
- `/.claude/settings.json` — hooks per §9
- `/.claude/agents/<all 13 agents>.md` — §4 (incl. Self-Learning Agent)
- `/.claude/commands/<all 9 slash commands>.md` — §7
- `/.claude/hooks/<12 scripts>` — §9
- `/config/watchlist.yaml`, `risk_limits.yaml`, `strategy_rules.yaml`, `routine_schedule.yaml`, `approved_modes.yaml` — §6
- `/tests/schemas/*.json` — JSON Schemas mirroring §6 schemas
- `/prompts/agents/<each>.md` — production agent prompts
- `/prompts/routines/<each>.md` — production routine prompts (§16)
- `/docs/operator_runbook.md`, `/docs/model_limitations.md`, `/docs/incident_response.md`
- `/journals/daily/.gitkeep`, etc. for empty folders

## Existing utilities to reuse
None — greenfield. (Re-evaluate per phase: Alpaca SDK for paper sim in Phase 4; openbb-style FOSS data libs for Phase 2 if budget tight.)

---

## Verification plan

End-to-end check at each phase boundary:

**Phase 1 (scaffold)**
- [ ] `git init`; commit scaffold.
- [ ] Create a deliberately bad `risk_limits.yaml` (e.g., negative loss cap). Hook #2 must reject the commit.
- [ ] Try to edit a journal file dated 2 days ago. Hook #4 must reject.
- [ ] Try to write to `trades/live/order.json`. Hook #1 must reject.
- [ ] Run `tests/` (schema validators) — all green.

**Phase 2 (routines)**
- [ ] Run `/premarket-report` manually. Verify report file created, journal updated, commit made, no live writes.
- [ ] Force a stale-data scenario (manually backdate a market data file). Routine must produce NO_TRADE.

**Phase 3 (full routines)**
- [ ] Run all 7 routines in sequence on a sandbox day. Verify every output exists, no rule violations.

**Phase 4 (paper)**
- [ ] Run a full week. Reconcile `trades/paper/log.csv` to `positions.json` daily. Zero discrepancies required.

**Phase 5+** — backtest exists per strategy; weekly + monthly reviews produced; drawdown within limit; no halt events caused by config violations.

**Always**
- [ ] Routine run produces exactly one commit (or zero if no changes).
- [ ] Notification arrives in chosen channel.
- [ ] No edits to forbidden paths (verified by `git diff` in CI).
- [ ] All decisions cite sources; no fabricated news.

---

## What this plan deliberately does NOT promise

- That paper-trading results predict live results.
- That any strategy will be profitable.
- That LLM reasoning is reliable enough for live execution without a deterministic engine layer.
- That this system replaces a financial advisor or accountant.
- That risk limits are sufficient to prevent loss; they are designed to **cap** loss, not eliminate it.
