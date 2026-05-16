You are running the self_learning_review routine for Calm Turtle.

Read and follow the steps in `prompts/routines/self_learning_review.md` exactly.
Use the `self_learning` subagent (which is observations-only in v1).

Comply with `CLAUDE.md` at the repo root throughout.

v1 scope: this routine writes to `memory/` (observation files only) and to
`reports/learning/` (weekly review report). It does NOT propose prompt
updates, strategy changes, or risk-limit changes — those are v2 capabilities
gated on `prompts/proposed_updates/.v2_enabled`. Until that flag is set,
proposals stay at zero.

Required reads: last 7 daily journals, `trades/paper/log.csv`,
`trades/paper/positions.json`, `memory/prediction_reviews/*.md`,
`memory/agent_performance/*.md`, regime memory.

Hard caps for this routine per `config/risk_limits.yaml > cost_caps`:
- Max self-learning proposals per cycle: 0 (v1 enforced)
- Max subagent dispatches per routine: as configured

Before exiting:
- Commit any new artifacts per the format in `docs/commit_messages.md`
  (subject: `self-learning: <YYYY-MM-DD> (M observations, K proposals drafted, J rejected)` —
  K should be 0 in v1).
- Notify via `lib.notify.send(...)` with: M observations written, top 2-3
  patterns noticed this week, any agent-performance flags.

If `config/approved_modes.yaml > mode == HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit cleanly. If it is `SAFE_MODE`, follow the SAFE_MODE handling section in `prompts/routines/self_learning_review.md` exactly: do NOT dispatch the `self_learning` subagent and skip every `memory/` learning write and `prompts/proposed_updates/` write (`memory/daily_snapshots/` remains allowed). Still write the `reports/learning/` summary, append `• Mode: SAFE_MODE (learning suppressed)` to the Telegram notification, and record `mode: SAFE_MODE` plus the skipped-step count in the routine audit.