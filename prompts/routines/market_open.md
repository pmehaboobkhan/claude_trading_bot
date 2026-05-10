# Market Open Routine — production prompt

> Scheduled 09:35 ET, Mon–Fri (5 minutes after open to let opening volatility settle). Use the `orchestrator` subagent.

You are running the **MARKET OPEN** routine for today.

1. Comply with `CLAUDE.md`. **When uncertain, NO_TRADE.**
2. Mode check + schema validation as in pre-market.
3. Load: today's `reports/pre_market/<date>.md` (the thesis), `trades/paper/positions.json`, the last 100 rows of `trades/paper/log.csv`, `memory/market_regimes/current_regime.md`.
4. `market_data`: live quotes for all 12 watchlist symbols + SPY + VIX. **Verify freshness** — any symbol with quote older than `risk_limits.yaml > data > max_data_staleness_seconds` is marked stale.
5. For each pre-market candidate (and any open position requiring action):
   a. `technical_analysis`: confirm thesis still valid against opening action.
   b. `trade_proposal`: produce a draft decision (`NO_TRADE` / `WATCH` / `PAPER_BUY` / `PAPER_SELL`).
   c. `risk_manager`: review against `risk_limits.yaml` + portfolio.
   d. `compliance_safety`: final gate.
6. Write each decision to `decisions/<date>/<HHMM>_<SYM>.json` (schema-validated).
7. **PAPER_TRADING mode only**: for `PAPER_BUY` / `PAPER_SELL` decisions approved by both gates, call `lib.paper_sim.open_position(...)` to append to `trades/paper/log.csv` and update `trades/paper/positions.json`. Reconcile.
8. Append per-symbol timeline rows to `decisions/by_symbol/<SYM>.md` for every decision (append-only).
9. Append a `## Market open` section to today's `journals/daily/<date>.md`.
10. Commit: `open: N decisions (P proposals, W watch, X no-trade)`.
11. Notify Telegram with a one-paragraph summary.

**Constraints**:
- `max_trades_per_day` cap applies — once exceeded, remaining proposals downgrade to `WATCH` automatically.
- Risk Manager always wins.
- Stale data → `NO_TRADE` for that symbol with reason `data_stale`.
- NO live execution under any circumstances.
