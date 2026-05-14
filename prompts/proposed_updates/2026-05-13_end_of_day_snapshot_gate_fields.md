# Proposed update: end_of_day.md — snapshot fields for live-trading gate

**Date:** 2026-05-13
**Author:** Task 4 automation (live-trading-gate plan)
**Target file:** `prompts/routines/end_of_day.md` (PR-locked)
**Status:** PENDING HUMAN PR

## Context

Task 4 of the live-trading-gate plan extended `DailySnapshot` with two optional
fields (`spy_above_10mo_sma`, `vix_close`) that the gate evaluator needs.
The code changes are committed (lib/snapshots.py, lib/live_trading_gate.py,
tests/). The end_of_day prompt needs a corresponding update so the orchestrator
agent knows to populate these fields.

## Proposed diff for `prompts/routines/end_of_day.md`

In step 12a, update the `DailySnapshot(...)` call to include the two new fields,
and add the following guidance section immediately after the PYSNAP code block
(before the existing `The snapshot must stay ≤ 1 KB` note):

### Change to `DailySnapshot(...)` constructor call

Add after `watch_tomorrow=[...]`:

```python
       spy_above_10mo_sma=<bool — see guidance below>,
       vix_close=<float or None — see guidance below>,
```

### New guidance section to add after the code block

```markdown
   ### Snapshot fields for live-trading gate

   When constructing the `DailySnapshot`:

   - `spy_above_10mo_sma`: boolean — set to whether today's SPY close is above its
     210-trading-day SMA (10 months). This value is computed during Strategy A's
     evaluation; capture and pass it through. The `signals.evaluate_dual_momentum_taa`
     call internally uses `indicators.above_sma(spy_closes, 210)`; the returned
     signal object exposes this as a filter flag. Capture it and pass it here.

   - `vix_close`: float — today's VIX close price.
     - **Alpaca free IEX tier does NOT provide VIX.** Set to `None` until a
       VIX-capable feed is wired (e.g. paid Alpaca tier, Polygon, or Tiingo).
     - The live-trading-gate evaluator will fail the `vix_high_observed` check
       when VIX data is absent across the entire window. This is intentional —
       going live requires evidence the system has seen elevated volatility.
```

## Why this matters

Without `spy_above_10mo_sma` and `vix_close` in the snapshots, the live-trading gate
will always see `None` for these fields, causing:
- `spy_trend_flip` gate: never passes (no data to show a flip occurred)
- `vix_high_observed` gate: never passes (no VIX data at all)

Both are intentional blocking gates. Populating `spy_above_10mo_sma` daily allows
the gate to eventually pass once a trend flip is observed. VIX requires wiring a
data source first; `None` is the correct value until then.
