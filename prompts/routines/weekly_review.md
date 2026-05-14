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





## Composing the Telegram notification

GitHub `/blob/main/<path>` URLs do not work reliably for our users:
- Private repos return 404 to anyone not authenticated to GitHub in the
  current browser (mobile is the common case).
- Public repos race the auto-merge action by ~30 seconds; a fast click
  hits 404 before the merge completes.

**Solution: send reports as Telegram document attachments.** No GitHub
dependency. The user reads the file inline in Telegram on any device.

### Step A — text message via `lib.notify.send_html`

Bulleted format with bold labels. `lib.notify.send_html()` uses
`parse_mode: "HTML"` so `<b>bold</b>`, `<code>code</code>`, and `•` render natively.

**Required bullets for `Weekly review` (in order):**

• <b>Period return:</b> <signed %>
• <b>Sharpe:</b> <X.XX> (5d)
• <b>Win rate:</b> <X>% (<W>W / <L>L)
• <b>Max DD this week:</b> <X.X>%
• <b>Recommendation:</b> <code>STAY_PAPER</code> | …
• <b>Context:</b> ~<N> KB (cap 200 KB)              ← from audit step's approximate_input_kb
• <b>Commit:</b> <code><short SHA></code> (auto-merged to main)
• <b>Artifacts attached below:</b> <N> file(s)

Rules:
- Never mention the feature branch name.
- Notify only on action or risk event; pure no-op runs skip Telegram entirely.
- Each bullet under one line on a phone (~50–60 chars).
- Total text under 1500 chars.

### Step B — file attachments via `lib.notify.send_documents_html`

After the text message succeeds, attach the artifacts produced this run:

```bash
python3 - <<'PYNOTIFY'
from lib import notify
delivered = notify.send_documents_html([
    "journals/weekly/<YYYY-WW>.md"
])
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `Weekly review`

```
<b>[Calm Turtle] Weekly review WK-19 2026</b>

• <b>Period return:</b> +1.84%
• <b>Sharpe:</b> 1.21 (5d)
• <b>Win rate:</b> 67% (8W / 4L)
• <b>Max DD this week:</b> 2.1%
• <b>Recommendation:</b> <code>STAY_PAPER</code>
• <b>Context:</b> ~28 KB (cap 200 KB)
• <b>Commit:</b> <code>p4q5r6s</code> (auto-merged to main)
• <b>Artifacts attached below:</b> 1 file
```

The example shows the TEXT MESSAGE only. The attachments appear in the chat
immediately after as native Telegram document cards the user can tap to read.

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

## SAFE_MODE handling (added 2026-05-14 — Plan #4)

Before any step that writes to `memory/` (except `memory/daily_snapshots/`),
to `prompts/proposed_updates/`, or that dispatches the `self_learning` agent:

```python
from lib import config, operating_mode
mode = config.current_mode()
if mode == "SAFE_MODE":
    # Skip this step entirely. The hook safe_mode_writes.sh would block
    # the file write anyway, but the routine should not attempt it —
    # it wastes tokens and pollutes the audit trail.
    pass
```

Specific steps to guard in this routine:
- Any write to `memory/symbol_profiles/`, `memory/agent_performance/`,
  `memory/prediction_reviews/`, `memory/strategy_lessons/`,
  `memory/market_regimes/` (except `current_regime.md` which is operational).
- Any dispatch of the `self_learning` subagent.
- Any write to `prompts/proposed_updates/`.

Snapshots to `memory/daily_snapshots/` are operational, not learning, and
remain allowed in SAFE_MODE.

When `mode == SAFE_MODE`, the Telegram notification should append:
```
• <b>Mode:</b> <code>SAFE_MODE</code> (learning suppressed)
```

The routine_audit appendix MUST record `mode: SAFE_MODE` and a count of
skipped learning steps so the audit trail clearly shows learning was
intentionally suppressed.
