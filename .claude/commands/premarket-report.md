---
description: Manually trigger the pre-market routine. Defaults to today's date.
argument-hint: "[YYYY-MM-DD]"
---

Run the pre-market routine for {{ $1 | default: today's date }}. Use the `orchestrator` subagent. Load `prompts/routines/pre_market.md` as the routine prompt. Produce `reports/pre_market/{{date}}.md`. Do NOT make trade decisions in this routine — that's `/market-open`. Commit and notify per the routine spec.
