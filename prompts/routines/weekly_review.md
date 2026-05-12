# Weekly Review Routine — production prompt

> Scheduled Saturday 09:00 ET. Use the `orchestrator` subagent.

You are running the **WEEKLY REVIEW** routine for the week ending today.

1. Comply with `CLAUDE.md`. No live data needed.
2. Schema validation.
3. Load: all `journals/daily/*.md` for the week, all `decisions/<date>/`, `memory/prediction_reviews/*.md`, `trades/paper/log.csv`, `memory/agent_performance/*.md`.
4. `performance_review` (metrics):
   - Period return (paper portfolio) vs **SPY** and vs **equal-weight 11 sector ETFs**.
   - Win rate, profit factor, max drawdown.
   - Per-strategy breakdown.
   - Per-agent calibration buckets vs realized hit rate.
   - Sample-size guardrail: mark anything with N < 20 as `PRELIMINARY`.
5. `self_learning` (interpretation):
   - Reconcile predictions whose 1d/5d window has closed: append outcome lines under each row in `decisions/by_symbol/<SYM>.md`.
   - Identify recurring mistakes.
   - Propose memory updates (apply `SAFE_MEMORY_UPDATE` directly to `memory/`).
   - Draft prompt updates → `prompts/proposed_updates/<date>_<topic>.md`. Cap: ≤ 5.
   - Draft strategy review docs → `prompts/proposed_updates/<date>_strategy_<name>.md`. Cap: ≤ 3.
   - Draft risk-rule review doc only if calibration drift is real → cap: ≤ 1.
6. Write `journals/weekly/<YYYY-WW>.md` and `reports/learning/weekly_learning_review_<date>.md` per the §21N template.
7. `compliance_safety`: verify no proposal silently modifies `risk_limits.yaml`, `strategy_rules.yaml`, `approved_modes.yaml`, or `watchlist.yaml`.
8. Commit: `weekly-review: <YYYY-WW> (win rate W%, profit factor PF, alpha vs SPY +/- X.X%)`.
9. Notify Telegram: "Weekly review ready. K proposed prompt updates, J risk lessons. Review report: <link>."

**Constraints**:
- NO direct edits to `config/`, `.claude/agents/`, or `prompts/routines/`. Drafts only.
- Recurring rejected proposals are tagged and silenced for 30 days.
- Every claim cites linked evidence.

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
