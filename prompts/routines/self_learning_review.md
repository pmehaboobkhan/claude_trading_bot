# Self-Learning Review Routine — production prompt

> Scheduled Sunday 10:00 ET. Use the `orchestrator` subagent. This is the dedicated learning cycle, separate from the weekly performance review (which runs Saturday and focuses on metrics).

You are running the **SELF-LEARNING REVIEW** routine.

1. Comply with `CLAUDE.md`.
2. Load: every memory file (`memory/**/*.md`), all per-symbol histories (`decisions/by_symbol/*.md`), prior weekly review, prior monthly review (if any), `prompts/proposed_updates/*` (so we can see what's already been drafted vs accepted vs rejected).
3. `self_learning` (lead, with `performance_review` providing metrics inputs):
   - Reconcile predictions whose outcome window has closed (1d / 5d / 20d horizons).
   - Update memory artifacts (observations only — `SAFE_MEMORY_UPDATE`).
   - Update calibration histograms in `memory/agent_performance/*.md`.
   - Update `memory/symbol_profiles/*.md` narrative sections.
   - Update `memory/market_regimes/history/<date>.md` with the regime that actually played out vs what we called.
   - Identify cross-cycle patterns: e.g., is one strategy systematically worse in regime X? Is one agent's confidence consistently miscalibrated?
   - Flag any agent whose calibration drift is concerning (especially Risk Manager and Compliance/Safety — those drift toward HALT_AND_REVIEW recommendation).
   - Cap proposals as in weekly review: ≤ 5 prompt-improvements, ≤ 3 strategy reviews, ≤ 1 risk-rule review.
4. `compliance_safety`: verify no proposal modifies a config or production prompt directly.
5. Write a brief `reports/learning/self_learning_<date>.md` summarizing the cycle.
6. Commit: `self-learning: <date> (M observations updated, K proposals drafted, J rejected)`.
7. Notify only if there are proposals that need human review or a calibration alert.

**Constraints**:
- This routine never makes trading decisions.
- It never overwrites a production prompt.
- It is allowed to update `memory/` observation files. Anything more substantive is a draft PR.
