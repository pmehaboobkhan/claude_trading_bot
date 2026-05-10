---
description: Manually request a paper-trade proposal for a watchlist symbol. Writes a decision file but does NOT auto-fill the paper log.
argument-hint: "<SYMBOL> [BUY|SELL]"
---

Propose a paper trade for symbol `$1` (side `$2`, default BUY).

1. Verify `$1` is in `config/watchlist.yaml` with `approved_for_paper_trading: true`. Refuse if not.
2. Verify current `approved_modes.yaml > mode` is `PAPER_TRADING` or higher. If `RESEARCH_ONLY`, write the decision but mark `final_status: REJECTED` with reason `mode_does_not_permit_trades`.
3. Use the `trade_proposal` subagent. Then route through `risk_manager` and `compliance_safety`.
4. Write the decision JSON to `decisions/<date>/<HHMM>_$1.json`.
5. Do NOT auto-fill `trades/paper/log.csv` — operator must run `/confirm-paper-trade <decision-file>` for that (this command is intentionally separate so manual proposals get a deliberate confirmation step).
6. Print a one-paragraph summary in chat with the path to the decision file.
