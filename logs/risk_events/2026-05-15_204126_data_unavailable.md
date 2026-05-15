# Risk event — market data unavailable at EOD

- timestamp: 2026-05-15T20:41:26Z
- type: data_unavailable / data_staleness_breach
- routine: end_of_day_2026-05-15
- severity: trade-blocking (NO_TRADE enforced), not ledger-corrupting
- actor: system (deterministic gate)

## What happened
At the EOD deterministic signal evaluation (step 4), the market-data layer
failed for **all 25 watchlist symbols**. The yfinance data host is blocked
at the network layer ("HTTP Error 403: Host not in allowlist") and no cached
fallback returned bars. Consequences:

- `signals.detect_regime` degraded to `regime=uncertain`, `confidence=low`,
  every indicator `null`, counter-evidence "Insufficient signal coherence".
- `signals.evaluate_all` emitted only the single data-free
  `gold_permanent_overlay` GLD ENTRY (a permanent-policy signal that needs
  no price input). No price-driven signals were computable.
- Most recent usable daily bar across the system remains **2026-05-08**
  (~7 calendar days stale), already flagged at pre-market and market_open.
- `data.max_data_staleness_seconds = 60` exceeded by orders of magnitude.

## Rule basis
- CLAUDE.md safety rule #5: stale data beyond max_data_staleness_seconds =>
  produce NO_TRADE, stamp staleness in the journal.
- CLAUDE.md "Handling missing data": market data stale => NO_TRADE for
  affected symbols, log to logs/risk_events/; missing input => more
  conservative, never less.
- "When uncertain, choose NO_TRADE."

## Action taken
- Book was already flat post the 2026-05-15T00:31:53Z fresh-start reset
  (`positions.json == {}`), so there were **no EXIT signals to process** and
  no positions exposed to the data gap.
- The single GLD ENTRY was routed to **NO_TRADE / REJECTED** via
  `decisions/2026-05-15/2041_GLD.json`
  (rejection_reason: data_unavailable_all_symbols AND data_staleness_breach).
- Circuit-breaker (step 5) still consulted for mandatory peak-tracking:
  state `FULL`, DD 0.00%, peak = current = $102,496.62, **no transition**.
- `lib.paper_sim.reconcile()` run per step 8 (see routine audit / journal).

## Secondary observation (env / operator-intent mismatch)
`logs/risk_events/2026-05-15_003153_state_reset.md` records operator intent
to run with `BROKER_PAPER=alpaca` (Alpaca paper-mirror mode). The actual
runtime environment has `BROKER_PAPER` **unset (= sim)**. No trade was
placed today so there is no mirror-divergence consequence, but the operator
should reconcile the env before the first post-reset entry actually lands —
otherwise fills will go to the internal sim ledger only, contrary to the
reset doc's stated intent. Tracked as a lessons-pending follow-up.

## Follow-up
- Data-feed restoration is the dominant operational headwind for the 4th
  consecutive session. NO_TRADE will persist every routine until a fresh
  daily bar is retrievable within the staleness cap.
- The recurring CB-peak-inflation failure mode is resolved by the reset
  (peak re-baselined to $102,496.62, CB now FULL) — that specific issue did
  NOT recur this run.
