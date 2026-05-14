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

**Required bullets for `Self-learning review` (in order):**

• <b>Period:</b> <start> → <end> (<N> trading days)
• <b>Observations written:</b> <N>
• <b>Top pattern:</b> <one-line summary> (N=<X>, <low/medium/high> confidence)
• <b>Proposals drafted:</b> <N> (v1 observations-only — should be 0)
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
    "reports/learning/weekly_learning_review_<YYYY-MM-DD>.md"
])
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `Self-learning review`

```
<b>[Calm Turtle] Self-learning review 2026-05-17</b>

• <b>Period:</b> 2026-05-12 → 2026-05-16 (5 trading days)
• <b>Observations written:</b> 4
• <b>Top pattern:</b> large_cap_momentum_top5 entries on FOMC weeks underperform (N=2, low confidence)
• <b>Proposals drafted:</b> 0 (v1 observations-only)
• <b>Context:</b> ~24 KB (cap 200 KB)
• <b>Commit:</b> <code>l1m2n3o</code> (auto-merged to main)
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
