# Monthly Review Routine — production prompt

> Scheduled 1st of month 09:00 ET. Use the `orchestrator` subagent.

You are running the **MONTHLY REVIEW** for the month just ended.

1. Comply with `CLAUDE.md`.
2. Schema validation.
3. Load: all weekly reviews for the month, full month of `decisions/`, `trades/paper/log.csv`, `memory/`.
4. `performance_review`:
   - Month return (paper) vs SPY vs equal-weight 11-sector buy-and-hold.
   - Sharpe-like (if N ≥ 30 trades or ≥ 30 trading days; otherwise mark `PRELIMINARY`).
   - Beta to SPY.
   - Information ratio.
   - Max drawdown vs SPY's.
   - Calibration trend month-over-month.
5. `self_learning` + `compliance_safety`:
   - Did we beat SPY risk-adjusted? Did we beat equal-weight 11-sector? Stamp both answers prominently.
   - **Mode recommendation** (the most important output of this routine):
     - `STAY_PAPER` (default if any concern, including under-performing equal-weight 11-sector on a 3-month rolling basis).
     - `PROPOSE_HUMAN_APPROVED_LIVE` — only if all phase-6 gates passed: ≥ 60 paper-trading days, ≥ 50 paper trades, beats both benchmarks risk-adjusted on 6-month basis, drawdown ≤ SPY's.
     - `HALT_AND_REVIEW` — if drawdown exceeds limits or systemic agent failure detected.
6. Write `journals/monthly/<YYYY-MM>.md` and `reports/learning/monthly_learning_review_<date>.md`.
7. Open PR drafts for any non-trivial proposed changes.
8. Commit: `monthly-review: <YYYY-MM> (recommendation: <STAY_PAPER|PROPOSE_HUMAN_APPROVED_LIVE|HALT_AND_REVIEW>)`.
9. Notify.

**Constraints**:
- The routine never recommends advancing more than one mode-step at a time.
- The routine NEVER recommends `LIVE_EXECUTION` directly. The most it can recommend is `LIVE_PROPOSALS`.
