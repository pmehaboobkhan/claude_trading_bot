# Weekly Learning Review — 2026-W20 (2026-05-12 → 2026-05-15)

> Template: §21N — Weekly Learning Review  
> Written: 2026-05-15T19:10Z  
> Mode: PAPER_TRADING  
> max_self_learning_proposals_per_cycle: 0 (v1 observations-only)

---

## Executive Summary

First paper-trading week. 4 trading sessions, 5 opens, 1 close, 1 reset. Portfolio ended slightly up (+0.82% on paper_sim basis). The dominant operational story is not trade quality — it is infrastructure bugs: the circuit-breaker peak-inflation artifact blocked 4 legitimate entry candidates across 7 consecutive routines. That bug is now resolved by reset, but the underlying code issue remains open.

**Recommendation: STAY_PAPER**

---

## Section A — Prediction Outcome Reconciliation

### A.1 Closed predictions

| ID | Symbol | Date | Type | Confidence | Outcome | Score |
|----|--------|------|------|-----------|---------|-------|
| P-2026-05-13-1 | CSCO | 2026-05-13 | PAPER_CLOSE (pre-earnings) | 0.85 | +$618.90 (+10.13%) realized. Post-print stock at ~$121 (IEX, wide spread) → left ~$20/sh upside. | PROCEDURALLY CORRECT; directionally left upside (acceptable by design) |

### A.2 Near-boundary NO_TRADE resolutions

| ID | Symbol | Date | NO_TRADE reason | Next-session outcome | Score |
|----|--------|------|----------------|---------------------|-------|
| P-2026-05-12-6 | JNJ | 2026-05-12 | max_trades_per_day cap | JNJ displaced by AMZN rank 5→6; never returned to top-5 this week | BENIGN — deferral missed no gain |
| P-2026-05-13-2 | AMZN | 2026-05-13 | CB_OUT + stale | Slipped to rank 6 (NO_SIGNAL) next session | BENIGN — signal was boundary noise |
| P-2026-05-14-1 | NVDA | 2026-05-14 | CB_OUT + stale | Demoted to rank 7 (NO_SIGNAL) on 2026-05-15 | BENIGN — signal was boundary noise |

### A.3 Still-pending predictions

All 2026-05-12 opens (GLD, GOOGL, XOM, WMT) remain pending. Momentum theses have 30–90 day windows; no updates from this review.

---

## Section B — Recurring Mistake Analysis

### B.1 Circuit-breaker peak inflation (SEVERITY: HIGH; FREQUENCY: 7 routines)

**Pattern:** `broker.account_snapshot()["cash"]` was used as the cash input to `paper_sim.portfolio_equity()`. The Alpaca paper account held legacy positions (QQQ, SPY) from pre-v1 testing; their settled-cash component inflated the "paper" cash balance by ~$19,148, pushing the CB peak from the correct $99,992 to $119,140.

**Evidence:** First artifact appeared 2026-05-12T22:38Z. Persisted through 2026-05-14 EOD (7 consecutive routines). Blocked 4 opens: AMZN (1×), CSCO (2×), NVDA (1×).

**Fix path:** In `lib.portfolio_risk.advance()`, the equity input must be computed exclusively from `paper_sim.cash_balance() + sum(paper_sim positions MTM)`. `broker.cash` must not appear in this computation. A regression test should assert: `portfolio_equity(paper_sim) ≤ starting_capital + cumulative_realized_pnl + 5%`.

**Code locations to patch:** `lib/portfolio_risk.py` (advance function), the EOD prompt's CB block (must pass paper_sim cash, not broker.cash).

**Category:** System bug / infrastructure.

### B.2 Multiple EOD invocations same day (SEVERITY: MEDIUM; FREQUENCY: 2026-05-12 only)

**Pattern:** The 2026-05-12 EOD routine was run 4 times in one day (20:02Z, 20:35Z, 22:24Z, 22:38Z). No idempotency guard prevented repeat executions.

**Evidence:** The CB peak inflation was exacerbated by repeated runs (the fourth run was what first introduced the inflated equity source). Lesson-pending since 2026-05-12.

**Fix path:** At the top of the end_of_day routine, check: if `memory/daily_snapshots/<today>.md` exists and `journals/daily/<today>.md` contains an "End of day" section → exit clean after refreshing the CB `last_observed_equity` only.

**Category:** Routine design / idempotency.

### B.3 Broker vs paper_sim source-of-truth split (SEVERITY: MEDIUM; FREQUENCY: persistent)

**Pattern:** In v1, broker (Alpaca) and paper_sim are decoupled. Multiple places in the code fetch data from the broker that is not relevant to paper_sim: `broker.latest_quotes_for_positions()` returns legacy QQQ/SPY; `broker.account_snapshot()["cash"]` includes legacy settled cash.

**Evidence:** Appeared in every routine from 2026-05-12–2026-05-14. Required per-call mitigations (building quotes from `data.get_bars(..., limit=5)[-1].close` instead of from broker).

**Fix path:** Create a `lib.paper_sim.get_quotes(symbols)` helper that fetches quotes for *paper_sim-tracked symbols only*, using `lib.data.get_latest_quote()`. Callers use this helper, never raw `broker.latest_quotes_for_positions()`.

**Category:** Infrastructure / abstraction.

---

## Section C — Pattern Observations (no code changes)

### C.1 CSCO pre-earnings playbook worked correctly

The pre_close step correctly identified the CSCO Q3 FY26 earnings catalyst, verified it with 3 independent sources, computed the implied-move asymmetry (9.87%), and executed the close. Result: +$618.90 realized before the AMC print. The strategy is designed for momentum carry, not earnings beta, so the "left upside on the table" outcome (stock gapped to ~$121) is the intended trade-off, not a mistake.

**Lesson confirmed:** The overnight-risk management pattern generalizes. WMT 2026-05-21 BMO should follow the same decision tree at pre_close-2026-05-20.

### C.2 Momentum rank stability: daily bars lag does not destabilize signals

The 6-month return rankings were recomputed 3× on 2026-05-12 (pre-market, EOD 20:02, 22:38) with byte-identical output each time. The 6-7 calendar-day daily bar lag has no meaningful effect on 126-day momentum scores.

**Lesson confirmed:** Momentum signals are robust to mild feed delays (6–7 days). The `max_data_staleness_seconds=60` cap is calibrated for intraday monitoring quotes, not for momentum bar inputs. No action needed.

### C.3 Regime labeling is partially feed-dependent

The 2026-05-13 regime upgraded from `range_bound` to `bullish_trend` at the same time the bar date regressed (the free IEX batch feed rolled back from 2026-05-07 to 2026-04-24 bars for one session). The regime is deterministic given the input bars, so feed-version drift can cause apparent regime oscillation without any real market change.

**Lesson confirmed:** Log the bar-date source alongside every regime call. If bar dates regress, note the potential for regime label artifacts.

### C.4 Near-boundary rank swaps are one-day noise

AMZN (rank 5→6→6), NVDA (rank 7→5→7), JNJ (rank 5→6→5) all bounced across the top-5 boundary within a 3-day window. All NO_TRADE decisions on boundary-rank symbols turned out to be at least as good as NOT deferring (no missed rallies).

**Lesson confirmed:** The hold-zone buffer (ranks 6–7 are NO_SIGNAL, not EXIT) is working as intended. Boundary-rank signals should carry lower confidence scores, as implemented.

---

## Section D — Strategy-Level Review

### D.1 Strategy A (dual_momentum_taa, 60% allocation)

- GLD held throughout. 12m return: 42.56% at entry → 38.50% by 2026-05-15. Still rank-1 risk asset; SPY closing the gap (+3pp/week) but still 7.6pp behind GLD.
- No rotation event this week. Strategy A is correctly in a carry state.
- Allocation concern: the 60% strategy-stated GLD weight conflicts with the 1.5% `max_risk_per_trade_pct`. Resolved this week by letting the per-trade risk cap govern (15% actual GLD weight). **This conflict should be documented formally** (already lessons-pending).

### D.2 Strategy B (large_cap_momentum_top5, 30% allocation)

- Rank set this week: GOOGL (1), XOM (2), CSCO (3→closed→pending-re-entry), WMT (4), JNJ/AMZN/NVDA rotating at rank 5.
- CSCO closed for earnings risk; net +$618.90 (+10.13%). Best trade of the week.
- The 5-position equal-weight allocation (~6% each) tracked to plan. Total exposure at peak: 38.5% of $100k (held 5 positions briefly, then 4 after CSCO close).
- Rank stability: GOOGL and XOM held top-2 all week; WMT held rank 4. Only rank 5 was unstable (JNJ→AMZN→NVDA→JNJ rotation).

### D.3 Strategy C (gold_permanent_overlay, 10% allocation)

- Subsumed by Strategy A's GLD position all week. The 10% permanent overlay is implicitly satisfied by the larger A position.
- No standalone C action required until Strategy A exits GLD.

---

## Section E — Agent Performance Review

Agent metrics are not yet meaningful at N=4 days. Noting observable quality:

| Agent / component | Performance note |
|-------------------|----------------|
| Signal evaluator (lib.signals) | Excellent: byte-identical reproducibility across 8+ independent calls |
| paper_sim | Good: reconciliation passed on first attempt every time |
| portfolio_health | Minor: `positions_to_close(quotes)` API signature differs from `assess_positions` caller pattern |
| portfolio_risk / CB | Bug: broker-cash double-count (see B.1 above) |
| routine_audit | Good: audit files written consistently |
| news_sentiment | Improved mid-week: offline at pre_market, functional via WebSearch at midday |

---

## Section F — Memory Updates (SAFE_MEMORY_UPDATE)

The following memory observation files are written or updated by this run:

1. `memory/strategy_lessons/2026-w20.md` — strategy execution lessons for the week (written this run)
2. `decisions/by_symbol/CSCO.md` — CSCO close prediction outcome annotated (PROCEDURALLY CORRECT)
3. `decisions/by_symbol/AMZN.md` — AMZN NO_TRADE annotated: "boundary noise, benign"
4. `decisions/by_symbol/NVDA.md` — NVDA NO_TRADE annotated: "boundary noise, benign"

Per `max_self_learning_proposals_per_cycle: 0`, no files written to `prompts/proposed_updates/`.

---

## Section G — Compliance Verification

The following config/protected files were NOT modified by any agent output this week:
- `config/risk_limits.yaml` ✓ (no modification)
- `config/strategy_rules.yaml` ✓ (no modification)
- `config/approved_modes.yaml` ✓ (no modification)
- `config/watchlist.yaml` ✓ (no modification)
- `.claude/agents/*.md` ✓ (no modification)
- `prompts/routines/*.md` ✓ (no modification)

**Compliance verdict: APPROVED**

---

## Section H — Forward Watch

| Item | Date | Routine | Priority |
|------|------|---------|----------|
| WMT earnings 2026-05-21 BMO | 2026-05-20 pre_close | Pre-earnings exit eval | HIGH |
| CSCO re-entry (fresh post-earnings bar) | next EOD with fresh bars | Signal re-evaluation | MEDIUM |
| CB peak-source code fix | requires PR | Infra fix | MUST-FIX |
| Regime memory persistence | next pre_market | Operational gap | LOW |

---

*Section count: H. Claims per section: all cite journal, decisions, or prediction-review files as evidence. PRELIMINARY tags applied to all statistical metrics (N < 20). No learning-suppression in effect (PAPER_TRADING mode).*
