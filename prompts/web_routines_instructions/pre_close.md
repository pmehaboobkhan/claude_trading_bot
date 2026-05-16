You are running the pre_close monitoring routine for Calm Turtle.

Read and follow the steps in `prompts/routines/pre_close.md` exactly. Use the
`orchestrator` subagent.

This is a MONITORING routine — you MUST NOT open new positions. Even if a
strong signal appears late-day, entries are committed to closing prices in
the end_of_day routine, not here.

Your job is to prepare the book for overnight risk: refresh the circuit-
breaker, run the standard stop/target health check, AND run an overnight-risk
overlay (any holding with earnings tomorrow? scheduled macro event tomorrow?).
Propose PAPER_CLOSE for positions facing material overnight exposure.

Comply with `CLAUDE.md` throughout.

Skip everything if no open positions exist.

If `mode == HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit.

Commit if any action happened OR any overnight-risk flag was raised.
Telegram with a short summary: holding N overnight, closing M, top reason.