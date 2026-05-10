---
description: Trigger the weekly review routine on demand.
argument-hint: "[YYYY-WW]"
---

Run the weekly review routine for {{ $1 | default: this week }}. Use the `orchestrator` subagent with `prompts/routines/weekly_review.md`. The routine should produce `journals/weekly/<YYYY-WW>.md` and `reports/learning/weekly_learning_review_<date>.md`. Open any proposed prompt updates as drafts in `prompts/proposed_updates/`.
