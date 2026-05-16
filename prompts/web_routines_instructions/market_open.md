You are running the market_open monitoring routine for Calm Turtle.

Read and follow the steps in `prompts/routines/market_open.md` exactly. Use the
`orchestrator` subagent to coordinate.

This is a MONITORING routine — you MUST NOT open new positions. ENTRY signals
from `lib.signals` are not acted on here. Your job is to refresh the
circuit-breaker with opening equity, detect overnight gaps that breached an
open position's stop/target, and propose PAPER_CLOSE for invalidated positions.
EXITs are never throttled.

Comply with `CLAUDE.md` throughout — capital preservation > clever trades.

If no open positions exist, skip steps 6–8 and exit cleanly.

If `mode == HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit.

Before exiting:
- Commit ONLY if action happened (close, CB transition, risk event). Pure
  no-op runs write a `logs/routine_runs/<ts>_market_open_noop.md` and skip
  the commit.
- Telegram notify only on action.