# Agent Performance — Orchestrator

This file tracks observable reliability and calibration of the pre-market / EOD orchestrator routine. Observations only; no verdicts.

## Raw reliability counts (cumulative)

| Metric | Value | Window |
|---|---|---|
| Pre-market runs observed | 2 | 2026-05-12 |
| Pre-market runs that completed all steps (snapshot + signals + report) | 1 | 2026-05-12 |
| Pre-market runs that produced a snapshot then exited without writing the report | 1 | 2026-05-12 |
| Manual recovery required | 1 | 2026-05-12 |

Completion rate (raw): 1/2 = 50%. Sample size 2 — far below any statistically meaningful threshold. Do not draw conclusions.

## Incident log

### 2026-05-12 — Incomplete pre-market run, manual recovery
- Source: `journals/daily/2026-05-12.md` line 19.
- Time window: 16:08-16:11 UTC.
- Symptom: orchestrator produced the deterministic market snapshot, then exited without writing `reports/pre_market/2026-05-12.md`.
- Recovery: human/operator re-ran the routine; the second run completed the full checklist.
- Impact on trading: none — pre-market is research-only and no decisions were written before recovery.
- Hypothesis (NOT a conclusion): there may be a fragility in the orchestrator's recovery path between the snapshot stage and the report-writing stage. Insufficient evidence to localize the cause.
- Counter-hypothesis to consider when more data arrives: this could be a one-off transient (process killed by environment, network blip, etc.) rather than a systematic bug.

## Calibration

Insufficient data. The orchestrator does not yet emit confidence-scored predictions of its own; calibration applies to downstream agents whose outputs the orchestrator coordinates.

## Open questions for future review (revisit at >= 50 paper trades or >= 90 trading days)

1. Does the incomplete-run pattern recur? If it appears again in cycles 2-4, escalate to a `STRATEGY_REVIEW_REQUIRED` (or, in v1, surface as an observation for the human to act on).
2. Is there a checkpoint between snapshot and report that, if absent, would make this failure mode silent in a live setting?
3. Should the orchestrator emit a heartbeat / completion record to `logs/routine_runs/` that downstream cycles can detect?

## Sources
- `journals/daily/2026-05-12.md` lines 18-21.
