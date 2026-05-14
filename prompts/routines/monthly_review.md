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

5a. **Live-trading gate evaluation** (must run before the mode recommendation):

```bash
python3 - <<'PYGATE'
import json, sys
from lib import config, live_trading_gate as gate

risk = config.risk_limits()
g = risk["gates"]
rd = g.get("regime_diversity_gates", {"enabled": False})

cfg = gate.GateConfig(
    enabled=True,
    minimum_paper_trading_days=g["minimum_paper_trading_days_before_live"],
    minimum_paper_trades=g["minimum_paper_trades_before_live"],
    minimum_sharpe=0.8,
    maximum_drawdown_pct=12.0,
    regime_diversity_enabled=rd.get("enabled", False),
    require_cb_throttle_event=rd.get("require_cb_throttle_event", False),
    require_spy_trend_flip=rd.get("require_spy_trend_flip", False),
    require_vix_high_observed=rd.get("require_vix_high_observed", 0.0),
    minimum_distinct_months=rd.get("minimum_distinct_months", 1),
)

# perf_summary must come from the performance_review subagent's step 4 output.
# It must contain: paper_trading_days, closed_paper_trades,
#                  portfolio_sharpe, portfolio_max_drawdown_pct.
perf_summary = json.loads(sys.stdin.read())
inputs = gate.load_default_inputs(performance_summary=perf_summary)
verdict = gate.evaluate_gates(cfg, inputs)
print(json.dumps({
    "overall_pass": verdict.overall_pass,
    "warning": verdict.warning,
    "gates": [
        {"name": g.name, "passed": g.passed, "actual": g.actual,
         "required": g.required, "note": g.note}
        for g in verdict.gates
    ],
}, indent=2))
PYGATE
```

   The orchestrator must:
   1. Take the JSON output from the `performance_review` subagent in step 4
      (must contain `paper_trading_days`, `closed_paper_trades`,
      `portfolio_sharpe`, `portfolio_max_drawdown_pct`).
   2. Pipe it as stdin into the gate-evaluator script above.
   3. Save the verdict JSON to
      `reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json`
      for the audit trail.

5b. **Mode recommendation** (consumes step 5a's verdict — the most important output):
   - If any CLAUDE.md halt trigger fired (drawdown > 12%, 3-month rolling return
     negative, or any individual strategy's drawdown > 25% on its allocated capital)
     → recommend `HALT_AND_REVIEW`. Cite the specific failing trigger.
   - Else if `verdict.overall_pass` is `True` AND `verdict.warning` is `null`
     → may recommend `PROPOSE_HUMAN_APPROVED_LIVE`. Constraint: never recommend
     more than one mode-step at a time — from `PAPER_TRADING` the next legal step
     is `LIVE_PROPOSALS` (NOT `LIVE_EXECUTION`).
   - Else if `verdict.warning` is not `null` (gates disabled in config)
     → recommend `STAY_PAPER` and surface the warning prominently in the journal
     and Telegram notification.
   - Else (one or more gates failed)
     → recommend `STAY_PAPER`. List the failing gate names in the rationale,
     e.g. `STAY_PAPER — failing gates: cb_throttle_event, vix_high_observed`.

6. Write `journals/monthly/<YYYY-MM>.md`, `reports/learning/monthly_learning_review_<date>.md`, and `reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json`.
7. Open PR drafts for any non-trivial proposed changes.
8. Commit: `monthly-review: <YYYY-MM> (recommendation: <STAY_PAPER|PROPOSE_HUMAN_APPROVED_LIVE|HALT_AND_REVIEW>)`.
9. Notify.

**Constraints**:
- The routine never recommends advancing more than one mode-step at a time.
- The routine NEVER recommends `LIVE_EXECUTION` directly. The most it can recommend is `LIVE_PROPOSALS`.





## Composing the Telegram notification

GitHub `/blob/main/<path>` URLs do not work reliably for our users:
- Private repos return 404 to anyone not authenticated to GitHub in the
  current browser (mobile is the common case).
- Public repos race the auto-merge action by ~30 seconds; a fast click
  hits 404 before the merge completes.

**Solution: send reports as Telegram document attachments.** No GitHub
dependency. The user reads the file inline in Telegram on any device.

### Step A — text message via `lib.notify.send`

Bulleted format with bold labels. `lib.notify.send()` already uses
`parse_mode: "Markdown"` so `*bold*` and `•` render natively.

**Required bullets for `Monthly review` (in order):**

• *Month return:* <signed %>
• *Annualized run-rate:* ~<X.X>% (N=<X> days)
• *Max DD MTD:* <X.X>%
• *Sharpe (MTD):* <X.XX>
• *Recommendation:* <STAY_PAPER | PROPOSE_HUMAN_APPROVED_LIVE | HALT_AND_REVIEW>
• *Gate:* <PASS|FAIL> (failing: <comma-separated gate names or "—">)
• *Context:* ~<N> KB (cap 200 KB)              ← from audit step's approximate_input_kb
• *Commit:* <short SHA> (auto-merged to main)
• *Artifacts attached below:* <N> file(s)

Rules:
- Never mention the feature branch name.
- Notify only on action or risk event; pure no-op runs skip Telegram entirely.
- Each bullet under one line on a phone (~50–60 chars).
- Total text under 1500 chars.

### Step B — file attachments via `lib.notify.send_documents`

After the text message succeeds, attach the artifacts produced this run:

```bash
python3 - <<'PYNOTIFY'
from lib import notify
paths = ["journals/monthly/<YYYY-MM>.md"]
# Attach the gate verdict JSON only when proposing a live-mode step — it's
# small enough to attach and the human reviewer will want to see which gates
# passed/failed before approving the PR.
if recommendation == "PROPOSE_HUMAN_APPROVED_LIVE":
    paths.append("reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json")
delivered = notify.send_documents(paths)
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `Monthly review`

```
*[Calm Turtle] Monthly review 2026-05*

• *Month return:* +1.92%
• *Annualized run-rate:* ~23.0% (N=11 days)
• *Max DD MTD:* 2.1%
• *Sharpe (MTD):* 1.18
• *Recommendation:* STAY_PAPER
• *Gate:* FAIL (failing: cb_throttle_event, vix_high_observed, distinct_calendar_months)
• *Context:* ~46 KB (cap 200 KB)
• *Commit:* t7u8v9w (auto-merged to main)
• *Artifacts attached below:* 1 file
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
