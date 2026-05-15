# Proposed update — `config/strategy_rules.yaml`

**Author:** Claude (assistant)
**Date:** 2026-05-14
**Status:** DRAFT — awaiting human PR review
**Reason:** `lib/signal_consolidator.py` (landed 2026-05-14) needs to know each strategy's portfolio allocation to decide which strategy wins a same-symbol convergence. The allocations are currently encoded as **prose** inside the `description` field of each `allowed_strategies[*]` entry, which means consolidator code can't read them and has to hard-code `STRATEGY_ALLOCATIONS` as a constant. Add a structured `allocation_pct` field so the consolidator (and any other tool needing the same data: backtest scripts, performance review, the Telegram report header) can read it from one place.

## What this changes

- Adds an `allocation_pct: float` field to each `allowed_strategies[*]` entry. The value is the portfolio fraction in decimal form (0.0–1.0).
- Updates `tests/schemas/strategy_rules.schema.json` to require the field on `ACTIVE_PAPER_TEST` strategies (REJECTED entries should still be allowed without it for audit-trail reasons).
- Updates `lib/signal_consolidator.py` to read from the config first, falling back to the hard-coded `STRATEGY_ALLOCATIONS` constant only if the field is absent (transitional period).

## Proposed addition to `config/strategy_rules.yaml`

```yaml
allowed_strategies:
  - name: dual_momentum_taa
    status: ACTIVE_PAPER_TEST
    allocation_pct: 0.60          # NEW: structured allocation field
    description: >-
      Trend-following + cross-asset momentum across SPY/TLT/GLD with SHV as cash floor.
      ...
  - name: large_cap_momentum_top5
    status: ACTIVE_PAPER_TEST
    allocation_pct: 0.30          # NEW
    description: >-
      ...
  - name: gold_permanent_overlay
    status: ACTIVE_PAPER_TEST
    allocation_pct: 0.10          # NEW
    description: >-
      Permanent 10% allocation to GLD ...
```

The three new values **must** sum to 1.0. Add a schema-level assertion or a runtime check in `lib.config.strategy_rules()`.

## Proposed addition to `tests/schemas/strategy_rules.schema.json`

```json
{
  "properties": {
    "allowed_strategies": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "status": { "type": "string", "enum": ["ACTIVE_PAPER_TEST", "NEEDS_MORE_DATA", "REJECTED"] },
          "allocation_pct": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
          "description": { "type": "string" }
        },
        "if": { "properties": { "status": { "const": "ACTIVE_PAPER_TEST" } } },
        "then": { "required": ["allocation_pct"] }
      }
    }
  }
}
```

## Proposed update to `lib/signal_consolidator.py`

After this lands, replace the hard-coded constant with a config-aware lookup:

```python
def _allocation_for(strategy: str, strategy_rules: dict | None = None) -> float:
    """Read allocation_pct from strategy_rules if present; fall back to the
    constant for the transitional period."""
    if strategy_rules is not None:
        for entry in strategy_rules.get("allowed_strategies", []):
            if entry.get("name") == strategy and "allocation_pct" in entry:
                return float(entry["allocation_pct"])
    return STRATEGY_ALLOCATIONS.get(strategy, 0.0)
```

`consolidate()` then takes an optional `strategy_rules` parameter and passes it through.

## Why this matters

Today the same numbers live in three places:
1. Prose in `config/strategy_rules.yaml > allowed_strategies > description`.
2. The constant in `lib/signal_consolidator.py > STRATEGY_ALLOCATIONS`.
3. Hard-coded `--alloc-a / --alloc-b / --alloc-c` defaults in `scripts/run_multi_strategy_backtest.py`.

When an allocation changes (e.g. the Strategy B reduction proposed in `plan.md > "Strategy B allocation review"`), three updates are required and the failure mode of forgetting one is silent. A single source of truth in the config eliminates the drift class.

## Verification once merged

```bash
# Schema must reject a config where allocations don't sum to 1.0 (if you add the runtime check)
python3 tests/run_schema_validation.py config/strategy_rules.yaml

# Consolidator reads the field
python3 -c "
from lib import config, signal_consolidator
rules = config.strategy_rules()
print(signal_consolidator._allocation_for('dual_momentum_taa', rules))
"  # → 0.60
```
