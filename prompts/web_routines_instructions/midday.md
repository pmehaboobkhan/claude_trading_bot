You are running the midday monitoring routine for Calm Turtle.

Read and follow the steps in `prompts/routines/midday.md` exactly. Use the
`orchestrator` subagent.

This is a MONITORING routine — you MUST NOT open new positions. Your job is
to refresh the circuit-breaker with midday equity, run a news scan against
the symbols where we have open positions, and propose PAPER_CLOSE on
news-driven or stop/target invalidations.

Comply with `CLAUDE.md` throughout.

Skip everything if no open positions exist.

Daily-loss limit utilization is rechecked here — if today's PnL breaches the
threshold, propose closing all positions and notify URGENT Telegram.

If `mode == HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit.

Commit and Telegram only if action happened.