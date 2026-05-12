# Self-Learning Observations — 2026-05-12

## Summary
- Trading days reviewed: **1** (2026-05-12)
- Paper trades executed: **0** (`trades/paper/log.csv` is empty placeholder; `trades/paper/positions.json` absent — confirmed by `journals/daily/2026-05-12.md` line 12)
- Predictions reconciled: **0** (no prior predictions exist)
- Memory files created this session: **5**
  - `memory/prediction_reviews/2026-05-12.md`
  - `memory/agent_performance/2026-05-12.md`
  - `memory/symbol_profiles/GLD.md`
  - `memory/symbol_profiles/GOOGL.md`
  - `memory/market_regimes/history/2026-05-12.md`
- Proposals drafted: **0** (v1 enforced; `config/risk_limits.yaml > cost_caps > max_self_learning_proposals_per_cycle: 0`; `prompts/proposed_updates/.v2_enabled` is absent)

## Observations

1. **System state transition recorded.** Mode flipped from `RESEARCH_ONLY` to `PAPER_TRADING` on 2026-05-11 and was confirmed at the 2026-05-12 pre-market check (`journals/daily/2026-05-12.md` line 5). Today is the first operational paper-trading session.

2. **Seven ENTRY signals were generated but zero decisions were written.** The pre-market run produced ENTRY signals for GLD (twice — once each for `dual_momentum_taa` and `gold_permanent_overlay`), GOOGL, XOM, CSCO, WMT, and JNJ (`journals/daily/2026-05-12.md` line 9). The journal explicitly notes "No trade decisions written (pre-market is research only)" (line 17). The signal-to-decision conversion is therefore an open data point for tomorrow's EOD reconciliation.

3. **The GLD double-count question is unresolved.** Two distinct strategies both signaled ENTRY on GLD today (`journals/daily/2026-05-12.md` line 9). The journal's next-session note (line 21) flags this as a reconciliation requirement before any decision is filed: "Reconcile GLD's Strategy A (60% macro ETF) vs Strategy C (10% permanent) allocations so they don't double-count."

4. **News data is structurally unavailable in v1.** The news connector is offline; all symbols are flagged `news_unavailable` and treated as a risk factor, not as bullish silence (`journals/daily/2026-05-12.md` line 15). This is consistent with CLAUDE.md's "Handling missing data" section. It is a known v1 limitation, not a defect.

5. **Recovery from a prior failed orchestrator run is documented.** A 16:08-16:11 UTC run on 2026-05-12 produced a snapshot but exited without writing the report (`journals/daily/2026-05-12.md` line 19). The session that did write the journal was a re-run. This is an operational observation; root cause is not investigated by this agent.

## Prediction reconciliation
No predictions exist yet. The first prediction log will begin once decisions are filed under `decisions/<date>/<HHMM>_<SYM>.json` with a `confidence_score` field. See `memory/prediction_reviews/2026-05-12.md` for the reconciliation schema (1d / 5d / 20d windows).

## Calibration baseline
All prediction counters initialized at zero across all agents (technical_analyst, fundamentals_analyst, news_sentiment, macro_regime, trade_proposal, risk_manager, compliance_safety, self_learning). See `memory/agent_performance/2026-05-12.md` for the per-agent table.

Per the v1 contract, calibration metrics require **N >= 30 reconciled predictions per agent** before any quality verdict is recorded. Portfolio-wide claims about agent calibration require **N >= 50 closed paper trades AND >= 90 trading days**. Neither threshold is close to being met.

## Data quality flags
- **News connector offline** (v1 structural limitation; `journals/daily/2026-05-12.md` line 15).
- **VIX unavailable**; 20d annualized realized vol used as proxy at 18.35% (line 8).
- **Market data latest bar = 2026-04-23** (Alpaca free IEX tier lag); acceptable for 6m/12m momentum but flagged for re-verification before any opens (line 16).
- **Fundamentals freshness**: not explicitly reported in today's journal. Will be tracked in future reviews per CLAUDE.md's 90-day rule.

## What failed / surprises
- **Prior orchestrator session exited without writing the report.** Recorded in `journals/daily/2026-05-12.md` line 19. The re-run succeeded. Root-cause investigation is out of scope for the self-learning agent; this is recorded for the operational record only.
- No actual P&L surprises possible (zero trades).

## Patterns (too early to judge)
With one day of operational data, any "pattern" claim would be over-fitting to a sample of one. Only structural observations are recorded:

- **Survivor bias in Strategy B.** Per `reports/learning/pivot_validation_2026-05-10.md`, the `large_cap_momentum_top5` backtest result (+1857% over 2013-2026) is inflated by selecting today's mega-caps. Realistic forward-return estimate: +10-14% CAGR. This is documented in `memory/symbol_profiles/GOOGL.md`.
- **Gold's expected-return / realized-return gap.** GLD's trailing 12m return today is +38.56%, but the backtest team's realistic forward estimate is +5-8% CAGR (`reports/learning/pivot_validation_2026-05-10.md`). The gap is large and worth tracking. See `memory/symbol_profiles/GLD.md`.
- **TLT / SPY co-movement risk.** Both fell in 2022 during the rate-hike cycle (per pivot_validation doc). The "three uncorrelated strategies" framing should be read in regime context, not as a constant property.

## Open questions for future review
- Once N >= 50 closed paper trades: revisit calibration histograms by confidence bucket and by agent.
- Once N >= 5 GLD trades closed: compare realized return to the +5-8% backtest forward estimate vs the +38.56% trailing 12m signal.
- Once a regime classifier has >= 20 calls reconciled against 5d / 20d SPY outcomes: evaluate whether "range_bound, low confidence" calls have any predictive power.
- After the news connector is added: redo the agent-performance baseline to include news_sentiment.

## Routine integrity
- v2 proposal pipeline check: `prompts/proposed_updates/.v2_enabled` not present — observations-only mode confirmed.
- No writes to `prompts/proposed_updates/`.
- No writes to `config/`, `.claude/agents/`, or `prompts/routines/`.
- No claims made without a source-file citation.
