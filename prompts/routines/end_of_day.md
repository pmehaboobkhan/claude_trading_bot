# End-of-Day Routine — production prompt

> Scheduled 16:30 ET, Mon–Fri. Use the `orchestrator` subagent. **`halt_on_error: true`** — this is the canonical journal finalization step.

You are running the **END-OF-DAY** routine.

1. Comply with `CLAUDE.md`.
2. Mode check + schema validation.
3. `market_data`: official close prices for all 12 watchlist symbols + SPY.
4. `performance_review`:
   - Today's PnL on paper portfolio.
   - Win rate, trade count.
   - Period-to-date metrics (week, month).
   - Update Cumulative-stats headers on `decisions/by_symbol/<SYM>.md` for any symbol that had activity today.
5. `journal`: finalize `journals/daily/<date>.md`. All required sections per the agent definition.
6. For every prediction made today, append an entry to `memory/prediction_reviews/<date>.md` with the prediction details (final review at weekly cadence).
7. Update `memory/agent_performance/<each_agent>.md` with today's hits/misses where determinable.
8. **Reconcile**: call `lib.paper_sim.reconcile()`. Any discrepancy → write `logs/risk_events/<ts>_reconcile.md` and notify URGENT.
9. `compliance_safety`: verify journal is complete; verify paper log matches `positions.json`.
10. Commit: `eod: journal + perf <date> (PnL ±$X.XX, N trades, win rate W%)`.
11. Notify Telegram: PnL, trade count, win rate, top lesson, mode for tomorrow.

**Constraints**:
- This routine is the only one that finalizes today's journal. After it commits, hook #4 makes the file immutable for future routine runs.
- Halt the routine if reconciliation fails — better one missed EOD report than a corrupted ledger.
