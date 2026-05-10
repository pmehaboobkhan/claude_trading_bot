# Self-Learning Review Routine — production prompt (v1: observations-only)

> Scheduled Sunday 10:00 ET. Use the `orchestrator` subagent.

## v1 operating mode: observations-only

Until **≥ 90 trading days AND ≥ 50 paper trades** are accumulated, this routine runs in observations-only mode (enforced by `self_learning` agent's prompt).

1. Comply with `CLAUDE.md`.
2. Load: every memory file, all per-symbol histories, prior daily journals.
3. `self_learning` (lead):
   - Reconcile predictions whose outcome window has closed (1d / 5d / 20d horizons): append outcome lines to `memory/prediction_reviews/<date>.md`.
   - Update calibration histograms in `memory/agent_performance/*.md` (raw numbers only — no verdicts).
   - Update `memory/symbol_profiles/*.md` with descriptive observations.
   - Update `memory/market_regimes/history/<date>.md` (regime called vs played out).
   - Write `reports/learning/observations_<date>.md` per the v1 format defined in the agent prompt.
4. `compliance_safety`: verify no writes to `prompts/proposed_updates/` (zero proposals in v1).
5. Commit: `self-learning: observations <date> (M memory files updated, K predictions reconciled)`.
6. Notify only if there's something operationally relevant (e.g., reconciliation gap, missing data).

## v2 mode (locked)
v2 mode opens **only** when both:
- `prompts/proposed_updates/.v2_enabled` exists (a human creates this file via PR).
- Sample size thresholds are met.

In v2, this routine also drafts prompt updates and review docs per the full self-learning loop. Until then, the proposal pipeline stays off.

## Why
LLMs are extremely prone to "explaining randomness as patterns." Below ~50 trades, any pattern we'd find is overwhelmingly likely to be noise. Self-Learning's value in v1 is *recording faithfully*, not *prescribing*.
