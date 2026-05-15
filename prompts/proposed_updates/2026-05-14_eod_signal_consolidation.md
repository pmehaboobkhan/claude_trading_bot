# Proposed update — `prompts/routines/end_of_day.md`

**Author:** Claude (assistant)
**Date:** 2026-05-14
**Status:** DRAFT — awaiting human PR review
**Reason:** Make GLD-convergence (and any future same-symbol multi-strategy ENTRY) deterministic at the routine layer instead of relying on the macro-ETF position cap to catch it. `lib/signal_consolidator.py` (landed 2026-05-14) provides the consolidation. This change wires EOD to consume `ConsolidatedSignal`s instead of raw `Signal`s.

## What this changes

Two changes to `prompts/routines/end_of_day.md`:

1. **After step 4** (deterministic signal evaluation), insert a consolidation step. The output is a list of `ConsolidatedSignal` objects.
2. **Steps 6 and 7** (EXIT and ENTRY handling) iterate `ConsolidatedSignal` instead of `Signal`. For each `ConsolidatedSignal` with `subsumed_strategies`, write a `*_subsumed.json` decision file in addition to the primary decision file — this gives the Self-Learning Agent + audit trail explicit visibility into which strategy's intent got absorbed.

The behavior matches what was already done manually for GLD on 2026-05-12 (see `decisions/by_symbol/GLD.md`, the "2026-05-12 — NO_TRADE (gold_permanent_overlay — subsumed)" entry). The deterministic code now produces that artifact automatically.

## Proposed addition: new step 4a in `prompts/routines/end_of_day.md`

> Insert between current step 4 (signal evaluation) and step 5 (circuit-breaker).

```markdown
4a. **Same-symbol signal consolidation**:
   ```bash
   python3 - <<'PYCONS'
   import json
   from lib import signal_consolidator
   raw_signals = [Signal(**s) for s in <signals from step 4>]
   consolidated = signal_consolidator.consolidate(raw_signals)
   print(json.dumps([
       {
           "symbol": cs.symbol,
           "action": cs.action,
           "primary_strategy": cs.primary_strategy,
           "subsumed_strategies": cs.subsumed_strategies,
           "conflict": cs.conflict,
           "rationale": cs.rationale,
       }
       for cs in consolidated
   ], indent=2))
   PYCONS
   ```

   - When `subsumed_strategies` is non-empty: the routine will open ONE position
     for the primary strategy and write a `*_subsumed.json` decision note for
     each subsumed strategy (see step 7).
   - When `conflict=True` (ENTRY+EXIT on the same symbol from different
     strategies): write `logs/risk_events/<ts>_signal_conflict.md` and send
     an URGENT Telegram notification. v1 does NOT auto-resolve — proceed with
     both signals as the routine layer would normally do (EXIT executes, ENTRY
     is then blocked by the risk manager's "already short of position" check).
```

## Proposed modification to step 7 (entry handling)

> Replace the existing step 7 with the following. Other steps unchanged.

```markdown
7. For each `ConsolidatedSignal` with `action == "ENTRY"` from an
   `ACTIVE_PAPER_TEST` strategy (note: `primary_strategy` is what we route on):
   - Verify symbol is in `watchlist.yaml` with `approved_for_paper_trading: true`.
   - Compute the intended position size per `risk_limits.yaml` (per-strategy /
     per-symbol caps). Size is based on the **primary strategy's allocation**,
     not the sum of contributing strategies — the whole point of consolidation
     is that the larger allocation absorbs the smaller one.
   - Apply the circuit-breaker throttle as before.
   - Have `trade_proposal` wrap as `PAPER_BUY` decision (one decision file:
     `decisions/<date>/<HHMM>_<SYM>.json`). Include `consolidation.subsumed`
     listing the subsumed strategy names in the decision JSON.
   - For each subsumed strategy, ALSO write a NO_TRADE decision file at
     `decisions/<date>/<HHMM>_<SYM>_<strategy>_subsumed.json` with:
     ```json
     {
       "action": "NO_TRADE",
       "reason": "subsumed_by_<primary_strategy>",
       "subsumed_under": "decisions/<date>/<HHMM>_<SYM>.json",
       "symbol": "<SYM>",
       "strategy": "<subsumed_strategy>"
     }
     ```
     These files are journaling-only; risk_manager and compliance_safety should
     skip them (they're already represented by the primary decision).
```

## Why we write subsumed-decision artifacts

Self-Learning Agent reads `decisions/<date>/*.json` to evaluate strategy hit-rate. Without the `*_subsumed.json` artifacts, the gold-overlay strategy looks like it never fired on days when TAA absorbed it — its hit-rate would be artificially zero. The artifacts let the agent count "strategy emitted ENTRY that was absorbed into primary" as a distinct outcome from "strategy was silent."

## Verification once merged

```bash
# Force the convergence case by stubbing out the regime so TAA picks GLD:
python3 -c "
from lib import signal_consolidator
from lib.signals import Signal
sigs = [
    Signal('GLD', 'ENTRY', 'dual_momentum_taa', {}, [], [], 'top-1', '...'),
    Signal('GLD', 'ENTRY', 'gold_permanent_overlay', {}, [], [], 'permanent', '...'),
]
for cs in signal_consolidator.consolidate(sigs):
    print(cs.primary_strategy, '|', cs.subsumed_strategies, '|', cs.rationale)
"
# Expected output:
#   dual_momentum_taa | ['gold_permanent_overlay'] | dual_momentum_taa:GLD:ENTRY [consolidated: subsumes gold_permanent_overlay on GLD ENTRY]
```
