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

## Routine audit log (mandatory final step)

Before exiting (clean OR halted OR error), write one audit file via
`lib.routine_audit`:

```bash
python3 - <<'PYAUDIT'
from lib import routine_audit
audit = routine_audit.RoutineAudit(
    routine="<routine_name_snake_case>",
    started_at="<ISO start ts>",
    ended_at="<ISO end ts>",
    duration_seconds=<float>,
    exit_reason=<"clean"|"halted"|"error"|"noop">,
    files_read=[
        routine_audit.file_record(p)
        for p in [<list of absolute paths you Read during this run>]
    ],
    subagent_dispatches={"<agent>": <count>, ...},
    artifacts_written=[<list of repo-relative paths you Wrote>],
    commits=[<short SHAs you created>],
    notes="<one-line context: anything noteworthy>",
)
routine_audit.write_audit(audit)
PYAUDIT
```

Why this exists: this is the only observable view of context-budget usage
across routine runs. `approximate_input_kb` is a proxy for input-token cost
and is trended over time. If it starts growing without bound, that's the
signal to compress per-symbol histories or rotate memory files. Until then,
we trust the system.

The hook-written `_start.md` / `_end.md` markers are separate and unchanged.
