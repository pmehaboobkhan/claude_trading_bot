You are running the pre_market routine for Calm Turtle.

Read and follow the steps in `prompts/routines/pre_market.md` exactly. Use the
`orchestrator` subagent to coordinate; it dispatches to specialist subagents
(market_data, news_sentiment, macro_sector, technical_analysis) per their
own definitions in `.claude/agents/`.

Comply with `CLAUDE.md` at the repo root throughout — capital preservation
> clever trades; when uncertain, NO_TRADE.

Before exiting:
- Commit any new artifacts per the format in `docs/commit_messages.md`
  (subject: `pre-market: research report <YYYY-MM-DD> (N candidates, regime=<x>)`).
- Notify via `lib.notify.send(...)` with a one-paragraph summary.

If `config/approved_modes.yaml > mode == HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit cleanly.