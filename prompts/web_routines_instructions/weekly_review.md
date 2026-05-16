You are running the WEEKLY REVIEW routine for Calm Turtle.

1. Read CLAUDE.md at the repo root and comply with every rule. No exceptions.
2. Read prompts/routines/weekly_review.md — that file is the spec for this routine. Execute every numbered step in order (1 through 9, plus 5b for the plain-English digest, plus the routine audit log step at the end).
3. The "current week" means the trading week ending today. If today is not a Saturday, still run for the most recent completed week.
4. Use the orchestrator subagent (.claude/agents/orchestrator.md) to dispatch the specialist subagents the prompt names (performance_review, self_learning, compliance_safety).
5. Telegram delivery is mandatory. The digest at reports/weekly_digest/<YYYY-WW>.md must be attached as the first document.
6. Commit once at the end per docs/commit_messages.md. Push to a feature branch and open a PR — do not push directly to main.

If approved_modes.yaml is HALTED, exit early after writing logs/routine_runs/. If it is SAFE_MODE, follow the SAFE_MODE handling section in the routine prompt (skip learning writes, still produce the digest, append the SAFE_MODE bullet to Telegram).