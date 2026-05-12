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

**Example for Self-learning review:**

```
*[Calm Turtle] Self-learning review 2026-05-17*

• *Period:* 2026-05-12 → 2026-05-16 (5 trading days)
• *Observations written:* 4
• *Top pattern:* large_cap_momentum_top5 entries on FOMC weeks underperform (N=2, low confidence)
• *Proposals drafted:* 0 (v1 observations-only)
• *Context:* ~24 KB (cap 200 KB)
• *Commit:* l1m2n3o (auto-merged to main)

*Report:* https://github.com/pmehaboobkhan/claude_trading_bot/blob/main/reports/learning/weekly_learning_review_2026-05-17.md
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
