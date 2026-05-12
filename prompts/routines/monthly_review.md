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



## Composing the Telegram notification

This routine commits to a `claude/...` feature branch (Claude Code default).
A GitHub Action immediately fast-forward-merges that branch into `main` and
deletes the source branch (see `.github/workflows/auto_merge_claude.yml`).
By the time the user reads your Telegram message, the feature branch is gone.

**Required format: bulleted, with bold labels.** Telegram renders Markdown
(`*bold*`) and the `•` character is a literal bullet that all clients
handle correctly. **Do NOT send prose paragraphs** — bullets are easier
to skim on mobile.

**Required fields, in order**, on each notification:

1. Header — `*[Calm Turtle] <routine title> <YYYY-MM-DD>*` on its own line.
2. One bulleted line per metric (regime, signals, PnL, etc. — see per-routine list below).
3. `• *Context:* ~<N> KB (cap 200 KB)` — populate N from the `approximate_input_kb`
   you computed in the audit step (sum of `files_read[].bytes` divided by 1024).
   This is a proxy for input-token cost, exposed so the user can spot context drift.
4. `• *Commit:* <short SHA> (auto-merged to main)` — short SHA only; never
   suffix with `on claude/<branch>`.
5. Artifact links (one per line), each as
   `*<Label>:* https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/<path>`.
   Use `/blob/main/<path>` — these resolve once the auto-merge completes
   (~30 seconds after push) and remain stable forever.

**Rules:**
- Never mention the feature branch name. Ever.
- Notify only if action was taken or a risk event fired. Pure no-op runs
  are logged to `logs/routine_runs/` but skip Telegram.
- Keep each bullet under one line on a phone (~50–60 chars). Truncate
  long thesis text and link to the full report instead.
- Total message length under 1500 chars; Telegram caps at 4096.

**Example for Monthly review:**

```
*[Calm Turtle] Monthly review 2026-05*

• *Month return:* +1.92%
• *Annualized run-rate:* ~23.0% (early — N=11 days)
• *Max DD MTD:* 2.1%
• *Sharpe (MTD):* 1.18
• *Recommendation:* STAY_PAPER
• *Context:* ~46 KB (cap 200 KB)
• *Commit:* t7u8v9w (auto-merged to main)

*Report:* https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/journals/monthly/2026-05.md
```

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
