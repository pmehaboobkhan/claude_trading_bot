# Pre-Close Routine — production prompt

> Scheduled 15:30 ET, Mon–Fri. Use the `orchestrator` subagent.

You are running the **PRE-CLOSE** routine.

1. Comply with `CLAUDE.md`.
2. Mode check + schema validation.
3. Load: open positions, today's decisions, today's PnL, regime memory.
4. `market_data`: end-of-day quotes for open positions.
5. `portfolio_manager`: hold-vs-close decision per open position.
   - If `mode != PAPER_TRADING`: log only; do not act.
   - If invalidation triggered or time-stop reached → `PAPER_CLOSE`.
   - If overnight risk (top-holding earnings tomorrow within `holding_earnings_caution_window_days`, scheduled macro event) → propose `PAPER_CLOSE`.
6. Route each proposal through `risk_manager` → `compliance_safety`.
7. Apply approved closes to paper log.
8. Append `## Pre-close` section to today's daily journal.
9. Commit: `pre-close: N hold, M close decisions`.
10. Notify with a short summary if any action was taken.

**Constraints**:
- We do NOT chase end-of-day moves. Closes are driven by invalidation/risk, not chart-watching.
- NO new positions opened pre-close.
