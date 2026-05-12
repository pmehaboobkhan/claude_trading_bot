# Self-Learning Observations — 2026-05-12

> v1 observations-only output. No proposals. No verdicts. Cite every claim.

## Cycle metadata
- Run date: 2026-05-12
- Mode: PAPER_TRADING (per `config/approved_modes.yaml`, confirmed in `journals/daily/2026-05-12.md` line 5).
- Trading days elapsed: 1 (paper mode activated 2026-05-11; today is the first full session under the self-learning framework).
- Decisions written this cycle: 0 (pre-market is research-only per journal line 17).
- Paper trades opened this cycle: 0 (`trades/paper/positions.json` absent per journal line 12).
- Paper trades closed this cycle: 0 (`trades/paper/log.csv` absent).
- Predictions reconciled this cycle: 0 (cold start — no prior predictions exist).
- Memory files initialized/updated this cycle: 9
  - `memory/prediction_reviews/2026-05-12.md`
  - `memory/agent_performance/orchestrator.md`
  - `memory/market_regimes/history/2026-05-12.md`
  - `memory/symbol_profiles/GLD.md`
  - `memory/symbol_profiles/GOOGL.md`
  - `memory/symbol_profiles/XOM.md`
  - `memory/symbol_profiles/CSCO.md`
  - `memory/symbol_profiles/WMT.md`
  - `memory/symbol_profiles/JNJ.md`
- Proposals drafted: 0 (v1: proposal pipeline locked at 0 until `prompts/proposed_updates/.v2_enabled` exists; flag verified absent at run time).

## Period
- Trading days: 1
- Decisions: 0
- Paper trades opened: 0
- Paper trades closed: 0
- Predictions reconciled this week: none (cold start)

## Predictions reconciled this week
None — this is cycle 1 and no predictions had been logged before today. See `memory/prediction_reviews/2026-05-12.md` for the 9 new prediction rows (7 ENTRY signals, 2 hold-zone signals) and 1 regime call opened today with 1d / 5d / 20d windows now ticking.

## Observations

1. **Cold start confirmed.** Paper mode activated 2026-05-11; no decisions or trades exist prior to today. `trades/paper/log.csv` and `trades/paper/positions.json` are both absent (`journals/daily/2026-05-12.md` line 12). Nothing to reconcile. (Descriptive only.)

2. **Today's pre-market produced 7 ENTRY signals across 6 distinct symbols.** GLD appears twice — once from Strategy A (`dual_momentum_taa`, +38.56% 12m) and once from Strategy C (`gold_permanent_overlay`, permanent 10%). The other five are Strategy B's top-5 by 6m return: GOOGL (rank 1, +35.31%), XOM (rank 2, +33.58%), CSCO (rank 3, +25.29%), WMT (rank 4, +24.30%), JNJ (rank 5, +20.17%, listed as alternate). Source: `journals/daily/2026-05-12.md` line 9; `data/market/2026-05-12/0630.json`; `reports/pre_market/2026-05-12.md`.

3. **GLD double-listing is flagged in the journal.** The EOD next-session context (journal line 21) explicitly notes the need to reconcile Strategy A's macro allocation against Strategy C's permanent 10% so total GLD exposure stays under the intended cap. Recorded as an open question in `memory/symbol_profiles/GLD.md`; no action proposed (v1).

4. **Two hold-zone (NO_SIGNAL within buffer) names recorded.** AMZN (rank 6, +14.87%) and NVDA (rank 7, +10.24%) sit just outside the top-5 rank cutoff. Logged in `memory/prediction_reviews/2026-05-12.md` as rows H01 and H02 with the implicit prediction "near-zero forward return relative to top-5 entries" — falsifiable in 5d / 20d.

5. **Regime call recorded:** range_bound, low confidence (journal line 8). Inputs: SPY +4.71% above 50d MA and above 200d MA; 20d annualized vol proxy 18.35%; VIX unavailable. The "low confidence" tag is consistent with the fact that the call uses bar data from 2026-04-23 (Alpaca free IEX tier lag, journal line 16). Logged in `memory/market_regimes/history/2026-05-12.md` with PENDING 5d / 20d outcomes.

6. **One orchestrator reliability event recorded.** Earlier pre-market run at 16:08-16:11 UTC produced a snapshot then exited without writing the report; recovery was a manual re-run of signals (journal line 19). Raw count: 1 incomplete out of 2 observed pre-market runs today. Sample size 2 — far below any meaningful threshold. Logged as a hypothesis (not a conclusion) in `memory/agent_performance/orchestrator.md`. A counter-hypothesis is also recorded: this could be a one-off transient. No proposal.

7. **No risk-rule breach observed.** Risk posture intact (journal line 13): 0/5 daily trades used, 0/8 open positions, daily-loss budget intact, circuit breaker at FULL band. Nothing to escalate.

## Signal quality notes

- **Top-5 by 6m return is concentrated in two sector-cluster classes today.** Of the 5 Strategy B candidates: GOOGL (mega-cap tech), XOM (energy / commodity-sensitive), CSCO (tech / networking), WMT (consumer staples), JNJ (healthcare). Two of the five names sit in tech-adjacent buckets (GOOGL, CSCO); the remaining three add non-tech diversity. This is a one-day observation — not a pattern. The relevant downstream question, when sample size permits, is whether Strategy B's top-5 systematically over-concentrates in any single sector. Recorded as open questions in `memory/symbol_profiles/XOM.md` and `CSCO.md`. (PRELIMINARY, N = 1 day.)
- **Rank-5 vs rank-6 spread is narrow.** JNJ at +20.17% (rank 5) vs AMZN at +14.87% (rank 6) → ~5.3 percentage-point gap. If subsequent sessions show frequent rank-5 / rank-6 swaps, Strategy B's transaction-cost drag becomes a concern. Recorded as an open question in `memory/symbol_profiles/JNJ.md`. No action proposed. (PRELIMINARY, N = 1 day.)
- **Momentum readings span 20% to 39%.** Highest is GLD (`dual_momentum_taa`, +38.56% 12m); lowest entry is JNJ at +20.17% 6m. The breadth of the surfaced list is consistent with a regime where momentum-positive names exist across sectors, which aligns with — though does not prove — the "trend-positive on SPY MA, but elevated vol" picture of today's regime call.

## Known data / infrastructure gaps

1. **News connector offline** (v1 limitation; CLAUDE.md known issue). Treated as a risk factor per project rule, not as bullish silence. Particularly material for JNJ (regulatory / litigation / trial events), GOOGL (regulatory / earnings revisions), and WMT (guidance updates). Recorded under each symbol profile.
2. **Bar staleness — latest tick 2026-04-23** (Alpaca free IEX tier lag, journal line 16). Acceptable for 6m / 12m momentum inputs; explicitly noted in the journal as something the EOD routine must re-verify before opening any positions. This will become a strict `NO_TRADE` blocker for affected symbols if it persists into a session where decisions are written (per CLAUDE.md "Handling missing data").
3. **VIX unavailable.** Regime call had to fall back to a 20d annualized vol proxy (18.35%) — recorded in `memory/market_regimes/history/2026-05-12.md`. When VIX is restored, future reviewers should compare proxy-vs-VIX readings on overlapping dates to assess substitution quality.
4. **Orchestrator recovery path fragility** — see Observation 6. Recorded with hypothesis + counter-hypothesis in `memory/agent_performance/orchestrator.md`.
5. **Earnings calendar not connected.** No way to systematically detect whether any of today's signals (notably CSCO, WMT, JNJ) sit on top of an imminent earnings event. Recorded under affected symbol profiles. Project-level limitation per CLAUDE.md.

## Calibration status

Insufficient data for any statistical calibration. Minimum thresholds before drawing calibration conclusions:
- 30 closed paper trades **or** 90 trading days (per v1 charter).
- Current: 0 trades, 1 trading day.

No agent has yet emitted a confidence-scored prediction whose outcome window has closed. The 9 prediction rows opened today are all PENDING. The orchestrator itself does not emit confidence scores; its observed reliability data point is recorded as a raw count (1 of 2 runs incomplete), not a calibration claim.

## Regime observation log

| Date | Call | Confidence | Inputs | 5d outcome | 20d outcome |
|---|---|---|---|---|---|
| 2026-05-12 | range_bound | low | SPY +4.71% > 50d MA; >200d MA; 20d vol proxy 18.35%; VIX n/a; bars to 2026-04-23 | PENDING (~2026-05-19) | PENDING (~2026-06-10) |

This is the first regime call recorded under the self-learning framework. No prior calls exist to compare against.

## Surprises
- The only surprise this cycle is the incomplete orchestrator run noted in Observation 6. Already logged; not interpreted as a pattern given N = 2.
- No symbol-profile contradictions to flag (no prior profile content exists yet).

## Open questions for future review (revisit when N >= 50 paper trades or >= 90 trading days)

1. Does the incomplete orchestrator-run pattern recur in cycles 2-4?
2. When the first GLD trade closes, did the Strategy A + Strategy C double-listing get correctly capped at total intended GLD exposure?
3. Does Strategy B's top-5 systematically over-concentrate in any single sector across sessions?
4. How frequently do rank-5 / rank-6 swaps occur in Strategy B's universe? (Proxy for churn / transaction-cost drag.)
5. When VIX data is restored, how does the 20d annualized vol proxy compare to VIX on overlapping dates?
6. When the news connector is restored, do material name-specific events appear in the lookback windows that would have changed the read for today's signals?

## What this routine cannot yet assess

- **Whether any signal was correct.** Outcome windows are all PENDING.
- **Whether any agent is well- or poorly-calibrated.** No predictions with closed windows.
- **Whether any strategy is performing as backtested.** Zero paper trades closed.
- **Whether the regime call is accurate.** 5d / 20d windows are open.
- **Whether the GLD double-count is actually causing oversized exposure.** No position has been opened to test the position-sizing logic.
- **Whether the orchestrator-incomplete-run is a systematic bug or a transient.** N = 2.
- **Any strategy-level claim.** v1 charter requires N >= 20 for strategy-level patterns; current N = 0.
- **Any symbol-specific behavioral claim.** v1 charter requires N >= 5 (with PRELIMINARY tag), or unmarked above that; current N = 1 day per symbol.

## Next-cycle focus areas (observation-side only)

- Reconcile each of the 9 prediction rows in `memory/prediction_reviews/2026-05-12.md` when the 1d window closes (~2026-05-13).
- Append any new orchestrator incidents to `memory/agent_performance/orchestrator.md` (do not edit existing rows).
- Update `memory/market_regimes/history/2026-05-12.md` outcome columns once 5d and 20d windows close.
- If any paper trade is opened in the next session, ensure a decision file exists under `decisions/2026-05-12/` (or future date) for that signal so the prediction-vs-realized chain stays auditable.

## Proposals
None. v1 charter: proposals locked at 0 until `prompts/proposed_updates/.v2_enabled` exists. The flag was verified absent at run time.

## Sources
- `journals/daily/2026-05-12.md`
- `reports/pre_market/2026-05-12.md` (referenced in journal line 11)
- `data/market/2026-05-12/0630.json` (referenced in journal line 7)
- `config/approved_modes.yaml` (referenced in journal line 5)
- `reports/learning/backtest_findings_2026-05-10.md`
- `reports/learning/pivot_validation_2026-05-10.md`
- `memory/prediction_reviews/2026-05-12.md` (initialized this cycle)
- `memory/agent_performance/orchestrator.md` (initialized this cycle)
- `memory/market_regimes/history/2026-05-12.md` (initialized this cycle)
- `memory/symbol_profiles/{GLD,GOOGL,XOM,CSCO,WMT,JNJ}.md` (initialized this cycle)
