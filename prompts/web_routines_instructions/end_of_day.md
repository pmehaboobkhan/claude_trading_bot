You are running the end_of_day routine for Calm Turtle.

Read and follow the steps in `prompts/routines/end_of_day.md` exactly. Use the
`orchestrator` subagent to coordinate; it dispatches to specialist subagents
(market_data, technical_analysis, portfolio_manager, risk_manager, trade_proposal,
journal, performance_review, compliance_safety) per their own definitions in
`.claude/agents/`.

Comply with `CLAUDE.md` at the repo root throughout — capital preservation
> clever trades; when uncertain, NO_TRADE.

This is the v1 paper-trade decision point. It runs the deterministic signal
evaluator, consults the Path Z circuit-breaker, opens/closes paper positions
via `lib.paper_sim`, reconciles, and finalizes today's journal.

Halt the routine immediately if reconciliation fails — better one missed
EOD than a corrupted ledger.

Before exiting:
- Commit any new artifacts per the format in `docs/commit_messages.md`
  (subject: `eod: journal + perf <YYYY-MM-DD> (PnL ±$X.XX, N trades, win rate W%, cb_state=<X>)`).
- Notify via `lib.notify.send(...)` with PnL, trade count, win rate, top
  observation, circuit-breaker state, and mode for tomorrow.

If `config/approved_modes.yaml > mode == HALTED`, write `logs/routine_runs/<ts>_halted.md` and exit cleanly.