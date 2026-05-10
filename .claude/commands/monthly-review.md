---
description: Trigger the monthly review routine on demand.
argument-hint: "[YYYY-MM]"
---

Run the monthly review routine for {{ $1 | default: this month }}. Use the `orchestrator` subagent with `prompts/routines/monthly_review.md`. Produce `journals/monthly/<YYYY-MM>.md` and `reports/learning/monthly_learning_review_<date>.md`. Include the **mode recommendation** (`STAY_PAPER` / `PROPOSE_HUMAN_APPROVED_LIVE` / `HALT_AND_REVIEW`) at the top of the report.
