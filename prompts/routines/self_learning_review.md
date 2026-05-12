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

## Composing the Telegram notification

The routine commits to a `claude/...` feature branch (Claude Code default).
A GitHub Action immediately fast-forward-merges that branch into `main`
and deletes the source branch (see `.github/workflows/auto_merge_claude.yml`).

This means: **by the time the user reads your Telegram message, the feature
branch no longer exists**. Never reference the feature branch by name in the
notification.

Compose links as follows:

- **Artifacts**: link to the file on the `main` branch using the form
  `https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/<path>`.
  These URLs resolve as soon as the auto-merge completes (~30 seconds after
  your push) and remain stable forever.
- **Commits**: cite the short SHA (e.g. `d10f9b6`). Do **not** suffix it
  with "on claude/<branch>" — commit SHAs are independent of branch refs
  and remain valid after the feature branch is deleted. If you want a
  clickable link, use `https://github.com/pmehaboobkhan/claude_trading_bot/commit/<sha>`.
- **Status**: it is fine to say "auto-merged to main" or to omit branch
  information entirely. Do not mention the feature branch name.

Example for pre_market:

```
[Calm Turtle] Pre-market 2026-05-12
Regime: range_bound (low confidence)
7 ENTRY signals; top candidate GLD (Strategy A + C agree)
Commit: d10f9b6 (auto-merged to main)
Report: https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/reports/pre_market/2026-05-12.md
Journal: https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/journals/daily/2026-05-12.md
```
