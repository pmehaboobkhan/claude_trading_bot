# Midday Routine — production prompt

> Scheduled 12:00 ET, Mon–Fri. Use the `orchestrator` subagent.

You are running the **MIDDAY** routine.

1. Comply with `CLAUDE.md`.
2. Mode check + schema validation.
3. Load: open positions, today's `decisions/<date>/`, `memory/market_regimes/current_regime.md`, intraday news.
4. `market_data` + `news_sentiment` for symbols with open positions.
5. `portfolio_manager`: for each open paper position, evaluate:
   - Has the original decision's `invalidation_condition` triggered?
   - Has the time-stop been hit?
   - Has stop-loss or take-profit triggered?
   Produce `PAPER_CLOSE` proposals for any "yes."
6. Route each proposed close through `risk_manager` → `compliance_safety`.
7. For approved closes in PAPER_TRADING mode, call `lib.paper_sim.close_position(...)`.
8. Append a `## Midday` section to today's daily journal.
9. **Commit only if anything changed** (a close, a risk event, a regime shift). If literally nothing happened, still write a `logs/routine_runs/<ts>_midday_noop.md` for audit.
10. Notify only if action was taken or a risk event occurred.

**Constraints**:
- NO opening of new positions in midday by default. Closes and risk-driven re-evaluation only.
- Daily-loss / consecutive-loss halts must be checked here too.
