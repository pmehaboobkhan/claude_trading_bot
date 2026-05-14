# Proposed update: monthly_review.md — wire live-trading gate evaluator

**Date:** 2026-05-13
**Author:** Task 5 automation (live-trading-gate plan)
**Target file:** `prompts/routines/monthly_review.md` (PR-locked via `block_prompt_overwrites.sh`)
**Status:** PENDING HUMAN PR

## Why

The monthly_review routine produces the recommendation that controls advancement
to live trading (`STAY_PAPER` / `PROPOSE_HUMAN_APPROVED_LIVE` / `HALT_AND_REVIEW`).
Today the recommendation is produced by `self_learning` + `compliance_safety`
subagents inspecting performance metrics directly, with the gate criteria
hard-coded in the prompt text.

After Tasks 1–4 of the live-trading-gate plan landed, we have a deterministic gate
evaluator (`lib.live_trading_gate.evaluate_gates`) that returns a structured,
machine-readable verdict. The recommendation **must** consult that verdict before
allowing `PROPOSE_HUMAN_APPROVED_LIVE`. Going live on benign-window paper evidence
alone (e.g. 90 days of smoothly trending market) is the canonical retail-quant
mistake; the gate adds regime-diversity checks (CB throttle event, SPY trend flip,
VIX ≥ 25, ≥ 4 distinct months) that prove the system has survived stress.

Current step 5 prompt criteria (`≥ 60 paper-trading days, ≥ 50 paper trades`)
are also inconsistent with `risk_limits.yaml` (`gates.minimum_paper_trading_days_before_live`
and `gates.minimum_paper_trades_before_live`). This change brings them into sync
by reading from config at runtime.

## Required prompt changes

### A. Replace step 5 with step 5a + 5b

**Current step 5:**

```markdown
5. `self_learning` + `compliance_safety`:
   - Did we beat SPY risk-adjusted? Did we beat equal-weight 11-sector? Stamp both answers prominently.
   - **Mode recommendation** (the most important output of this routine):
     - `STAY_PAPER` (default if any concern, including under-performing equal-weight 11-sector on a 3-month rolling basis).
     - `PROPOSE_HUMAN_APPROVED_LIVE` — only if all phase-6 gates passed: ≥ 60 paper-trading days, ≥ 50 paper trades, beats both benchmarks risk-adjusted on 6-month basis, drawdown ≤ SPY's.
     - `HALT_AND_REVIEW` — if drawdown exceeds limits or systemic agent failure detected.
```

**Replace with:**

```markdown
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
        {
            "name": g.name,
            "passed": g.passed,
            "actual": g.actual,
            "required": g.required,
            "note": g.note,
        }
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
   - If any CLAUDE.md halt trigger fired (drawdown > 12 %, 3-month rolling return
     negative, or any individual strategy's drawdown > 25 % on its allocated capital)
     → recommend `HALT_AND_REVIEW`. Cite the specific failing trigger.
   - Else if `verdict.overall_pass` is `True` **AND** `verdict.warning` is `null`
     → may recommend `PROPOSE_HUMAN_APPROVED_LIVE`. Constraint: never recommend
     more than one mode-step at a time — from `PAPER_TRADING` the next legal step
     is `LIVE_PROPOSALS` (NOT `LIVE_EXECUTION`).
   - Else if `verdict.warning` is not `null` (gates disabled in config)
     → recommend `STAY_PAPER` and surface the warning prominently in the journal
     and Telegram notification.
   - Else (one or more gates failed)
     → recommend `STAY_PAPER`. List the failing gate names in the rationale,
     e.g. `STAY_PAPER — failing gates: cb_throttle_event, vix_high_observed`.
```

### B. Telegram notification: add gate verdict bullet

In the **Step A — text message** section, append after the existing
`*Recommendation:*` bullet:

```
• *Gate:* <PASS|FAIL> (failing: <comma-separated gate names or "—">)
```

Note: if the HTML-mode notification migration (commit 0515e62) has landed,
use `<b>Gate:</b>` instead of `*Gate:*`.

Updated example notification block:

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

### C. Step 6: include gate verdict JSON in artifacts

Update step 6 to add the gate verdict file to the list of artifacts written:

```markdown
6. Write `journals/monthly/<YYYY-MM>.md`,
   `reports/learning/monthly_learning_review_<date>.md`, and
   `reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json`.
```

Also pass the gate verdict JSON to `send_documents` in the Telegram step B
only if the recommendation is `PROPOSE_HUMAN_APPROVED_LIVE` (it's small enough
to attach and the human reviewer will want it):

```python
from lib import notify
paths = ["journals/monthly/<YYYY-MM>.md"]
if recommendation == "PROPOSE_HUMAN_APPROVED_LIVE":
    paths.append("reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json")
delivered = notify.send_documents(paths)
```

## Files affected

- `prompts/routines/monthly_review.md` (this PR's target — hook-locked)
- No config changes. No lib changes.

## Tests / smoke check after PR merges

### 1. Schema validation

```bash
python3 tests/run_schema_validation.py
```

Expected: all PASS.

### 2. Synthetic gate smoke test (no real data needed)

```bash
echo '{"paper_trading_days": 5, "closed_paper_trades": 0, "portfolio_sharpe": 0.0, "portfolio_max_drawdown_pct": 0.5}' | python3 -c "
import json, sys
from lib import live_trading_gate as gate
perf = json.loads(sys.stdin.read())
cfg = gate.GateConfig(
    enabled=True, minimum_paper_trading_days=90, minimum_paper_trades=30,
    minimum_sharpe=0.8, maximum_drawdown_pct=12.0,
    regime_diversity_enabled=True, require_cb_throttle_event=True,
    require_spy_trend_flip=True, require_vix_high_observed=25.0,
    minimum_distinct_months=4,
)
inputs = gate.load_default_inputs(performance_summary=perf)
verdict = gate.evaluate_gates(cfg, inputs)
print('overall_pass:', verdict.overall_pass)
print('warning:', verdict.warning)
for g in verdict.gates:
    print(f'  {g.name}: {\"PASS\" if g.passed else \"FAIL\"} (actual={g.actual}, required={g.required})')
"
```

Expected output (verified 2026-05-13 — current early-paper-trading state):

```
overall_pass: False
warning: None
  paper_trading_days: FAIL (actual=5, required=90)
  closed_paper_trades: FAIL (actual=0, required=30)
  portfolio_sharpe: FAIL (actual=0.0, required=0.8)
  portfolio_max_drawdown: PASS (actual=0.5, required=<= 12.0)
  cb_throttle_event: FAIL (actual=0, required=>= 1 FULL->HALF or HALF->OUT transition)
  spy_trend_flip: FAIL (actual=no flip, required=At least one SPY 10mo-SMA filter change in window)
  vix_high_observed: FAIL (actual=0, required=>= 25.0)
  distinct_calendar_months: FAIL (actual=1, required=4)
```

With 7 of 8 gates failing and `overall_pass: False`, the routine would produce
`STAY_PAPER` — the correct safe-default for early paper trading.

### 3. End-to-end acceptance test

Running the actual monthly_review routine against a synthetic month is the real
acceptance test, deferred to operator. The routine should:
- Run step 5a, produce the gate verdict JSON, save it under `reports/learning/`.
- In step 5b, print `STAY_PAPER — failing gates: paper_trading_days, closed_paper_trades, ...`.
- Telegram notification includes the `*Gate:* FAIL (...)` bullet.

## Reviewer checklist

- [ ] Step 5 text replaced with 5a + 5b as specified above.
- [ ] `perf_summary` piped from step 4 `performance_review` output (not re-computed).
- [ ] Gate verdict JSON saved to `reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json`.
- [ ] Telegram bullet `*Gate:*` added after `*Recommendation:*`.
- [ ] Halt trigger check (step 5b first branch) still cites CLAUDE.md thresholds.
- [ ] `PROPOSE_HUMAN_APPROVED_LIVE` path requires `overall_pass AND warning is null`.
- [ ] Old hard-coded gate criteria (`≥ 60 days, ≥ 50 trades`) fully removed from prompt.
