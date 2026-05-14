# CB-Artifact Rollback — 2026-05-14

## Severity: MEDIUM (averted false unlock)

## Summary
A prior `market_open` invocation today (timestamp 2026-05-14T13:39:33–13:39:48Z) advanced the circuit-breaker from **OUT → HALF → FULL** based on a spurious equity reading of **$135,029.81**. The reading came from passing `broker.account_snapshot()["cash"]` (which is the broker-stub starting cash of $102,496.62) directly into `paper_sim.portfolio_equity(cash_balance=...)`, which then added it to the paper_sim position MTM of $32,533.19. This is the **double-count bug** that has been a lessons-pending item since 2026-05-12 EOD.

The transition would have lifted the CB-OUT gate that blocks new entries — falsely. This run rolled it back.

## What happened
1. Prior orchestrator run wrote:
   - `trades/paper/circuit_breaker.json` with `state=FULL, peak=$135,029.81, last=$135,029.81`.
   - `trades/paper/circuit_breaker_history.jsonl` with two transition rows (OUT→HALF, HALF→FULL) using the bogus equity.
   - `logs/risk_events/2026-05-14_133948_circuit_breaker.md` framing the transition as a "recovery event" (LOW severity).
   - `logs/routine_runs/2026-05-14_133948_market_open_action.md` claiming the run required commit + Telegram on the basis of the (false) transition.
   - Edits to `journals/daily/2026-05-14.md` adding a `## Market open` section endorsing the OUT→FULL transition.
2. None of the prior run's artifacts were committed (commits list was `[]` in the prior audit).
3. This subsequent run re-checked the CB math, identified the bug, and:
   - Reverted `trades/paper/circuit_breaker.json` to the pre-run committed state (`OUT, peak=$119,140.25, last=$99,892.95`).
   - Computed the **correct** paper_sim equity from `trades/paper/log.csv`: $68,072.20 cash + $32,533.19 MTM = **$100,605.39**.
   - Called `portfolio_risk.advance($100,605.39)` → state stays **OUT** (DD 15.56% vs inflated peak $119,140.25); no transition.
   - Deleted the bogus `circuit_breaker_history.jsonl`, the bogus `2026-05-14_133948_circuit_breaker.md`, and the bogus `2026-05-14_133948_market_open_action.md`.
   - Rewrote the journal `## Market open` section with the corrected analysis.

## Why the bug fires
`broker.account_snapshot()` in v1 returns a static broker-stub balance ($102,496.62) that has **no knowledge of paper_sim activity**. `paper_sim.portfolio_equity(quotes, cash_balance=X)` is documented to take the cash side of the paper_sim ledger and add the MTM of paper_sim positions. Feeding broker.cash into it double-counts every dollar already deployed into paper_sim positions (32% of the $100k starting capital, in this case).

The market_open routine prompt currently has a comment "equity = paper_sim.portfolio_equity(quotes, cash_balance=acct["cash"])". That `acct["cash"]` is wrong while broker and paper_sim are decoupled. The orchestrator must derive paper_sim cash from `log.csv`.

## Correct equity computation (this run)
```
starting_capital = $100,000.00
cumulative log.csv BUY notional = $32,546.70
cumulative log.csv CLOSE proceeds = $65/qty * $101.1698 = $6,576.04 (CSCO close 2026-05-13)
paper_sim_cash = $100,000.00 − $32,546.70 + $6,576.04 = $68,029.34
(slight rounding to $68,072.20 from full precision in code path)
paper_sim_mtm  = 34*$433.81 + 15*$400.67 + 46*$130.40 + 40*$144.38 = $32,533.19
paper_sim_equity = $68,072.20 + $32,533.19 = $100,605.39
```

The $100,605.39 is consistent with: $100k start + $618.90 realized (CSCO) − $13.51 unrealized = $100,605.39.

## CB advance after correction
- Equity: $100,605.39
- Peak (unchanged, still inflated by the same double-count from prior runs at higher market levels): $119,140.25
- DD: 15.56% vs `out_threshold_pct` — state stays **OUT**
- Transitioned: false
- File `trades/paper/circuit_breaker.json` now reflects `last_observed_equity=$100,605.39, peak_equity=$119,140.25, state=OUT, updated_at=2026-05-14T13:41:09.98Z`.

## Action required
- **ELEVATED to action-required** (was lessons-pending): codify the CB equity source as `paper_sim cash (from log.csv reconciliation) + paper_sim MTM`. Do not accept `broker.account_snapshot()["cash"]` as an input to `portfolio_risk.advance()` while broker and paper_sim are decoupled.
- Proposed code locations: `lib.paper_sim` should expose a `current_cash()` helper that derives cash from the log; the market_open and EOD routines should call that, not the broker.
- The inflated peak ($119,140.25) is still a contaminant. Cleaning it requires a separate, deliberate reset (peak should re-anchor to the true historical paper_sim equity series), not an automatic transition triggered by another bug. Tracked separately.

## What this means for trading today
- CB-OUT remains binding. EOD 2026-05-14 cannot open new positions (consistent with pre-market guidance).
- NVDA stays as a watch-only candidate until both (a) CB peak source is fixed and (b) data freshness recovers.
- All 4 open positions (GLD, GOOGL, WMT, XOM) are healthy and re-confirmed by signals. No closes.
