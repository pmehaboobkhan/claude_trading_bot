You are running the MONTHLY REVIEW routine for Calm Turtle.

1. Read CLAUDE.md at the repo root and comply with every rule. No exceptions.
2. Read prompts/routines/monthly_review.md — that file is the spec for this routine. Execute every numbered step in order (1 through 9, including 5a the live-trading-gate evaluation and 5b the mode recommendation, plus the routine audit log step at the end). Do not duplicate or paraphrase the spec here — follow that file exactly; it is the single source of truth.
3. "The month just ended" means the most recently completed calendar month. If today is not the 1st, still run for that most recent completed month.
4. Use the orchestrator subagent (.claude/agents/orchestrator.md) to dispatch the specialist subagents the spec names (performance_review, self_learning, compliance_safety).
5. Telegram delivery is mandatory. Attach journals/monthly/<YYYY-MM>.md as the first document. Attach reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json as a second document ONLY when the recommendation is PROPOSE_HUMAN_APPROVED_LIVE.
6. Commit once at the end per docs/commit_messages.md (subject: `monthly-review: <YYYY-MM> (recommendation: <STAY_PAPER|PROPOSE_HUMAN_APPROVED_LIVE|HALT_AND_REVIEW>)`). Push to a feature branch and open a PR — do not push directly to main.

Hard safety guardrails (the spec enforces these; never override them):
- Never recommend advancing more than one mode-step at a time. From PAPER_TRADING the only legal next step is LIVE_PROPOSALS.
- NEVER recommend LIVE_EXECUTION directly. The most this routine may ever recommend is LIVE_PROPOSALS.
- If any CLAUDE.md halt trigger fired (drawdown > 12%, 3-month rolling return negative, or any individual strategy's drawdown > 25% on its allocated capital), recommend HALT_AND_REVIEW and cite the specific failing trigger.

If approved_modes.yaml is HALTED, exit early after writing logs/routine_runs/. If it is SAFE_MODE, follow the SAFE_MODE handling section in the routine prompt: skip every learning write (memory/ except daily_snapshots, prompts/proposed_updates/) and any self_learning dispatch, still produce the monthly report and the gate verdict, append `• Mode: SAFE_MODE (learning suppressed)` to the Telegram notification, and record `mode: SAFE_MODE` in the routine audit.
