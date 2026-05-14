# Tighten Live-Trading Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current "90 days + 30 trades + Sharpe + DD" unlock criteria with a regime-diversity-aware gate that requires the system to have survived at least one stress event before live trading is permitted.

**Architecture:** Three changes that move together. (1) `config/risk_limits.yaml` gains a `regime_diversity_gates` block (additive, schema-validated). (2) A new pure helper `lib/live_trading_gate.py` computes which gates have been satisfied from current paper-trading history (CB state log, paper-trade log, daily snapshots). (3) `prompts/routines/monthly_review.md` is updated to call the helper and surface verdicts in the recommendation. CLAUDE.md's "Live-trading unlock criteria" block is updated to match.

**Tech Stack:** Python 3.12, existing `lib.config`, `lib.portfolio_risk`, `lib.snapshots`. Pure stdlib; no new deps.

---

## Why this matters (one paragraph for the executor)

Current unlock criteria — 90 days, 30 trades, Sharpe ≥ 0.8, DD ≤ 12% — can all be satisfied by a benign 90-day stretch of trending market. That's exactly the regime where the strategy is *expected* to look good. Going live on the basis of evidence from a friendly environment is the canonical retail-quant mistake. We need at least one piece of stress-test evidence: a CB throttle event, a notable VIX spike, or a SPY trend-flip that the system actually survived in paper. The reviewer was right; this gate is too weak.

---

## File Structure

**Create:**
- `lib/live_trading_gate.py` — pure helpers: read CB history + paper log + snapshots, return per-gate pass/fail with citations.
- `tests/test_live_trading_gate.py` — pure-function tests with synthetic inputs (no real history).

**Modify:**
- `config/risk_limits.yaml` — add `regime_diversity_gates` block under `gates:`.
- `tests/schemas/risk_limits.schema.json` — extend the `gates` schema.
- `lib/portfolio_risk.py` — extend `save_state` (or add a sibling) to append to a CB-event log so the gate can audit historical transitions. (Currently `save_state` overwrites; we need history.)
- `tests/test_portfolio_risk.py` — add tests for the new event-log append.
- `prompts/routines/monthly_review.md` — call the gate helper; surface the verdict in the recommendation logic and Telegram bullets.
- `CLAUDE.md` — replace the "Live-trading unlock criteria" block.

**No edits to:**
- Any agent prompt under `prompts/agents/` (gate is only consumed by the monthly_review routine).
- `config/approved_modes.yaml`.
- Any production strategy code.

---

## Task 1: Add CB-event history (append-only log)

**Files:**
- Modify: `lib/portfolio_risk.py`
- Modify: `tests/test_portfolio_risk.py`
- Create: `trades/paper/circuit_breaker_history.jsonl` (file will be auto-created on first event)

The current `save_state` overwrites `circuit_breaker.json` with the latest snapshot. The gate needs to know about historical transitions (FULL→HALF, HALF→OUT, etc.). Cheapest reliable mechanism: append a one-line JSON record to a sibling history file every time the state *changes*.

- [ ] **Step 1: Read the existing `advance()` function**

```bash
sed -n '180,260p' /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/lib/portfolio_risk.py
```
Expected: locate `advance()`. Note where it calls `save_state` and where it has access to the previous state vs the new state. The transition fact (`old_state != new_state`) is computable here.

- [ ] **Step 2: Write the failing test**

In `tests/test_portfolio_risk.py`, add:

```python
def test_advance_appends_history_on_state_change(tmp_path, monkeypatch):
    """When advance() flips state, it appends a JSONL row to circuit_breaker_history.jsonl."""
    import json
    from lib import portfolio_risk as pr

    state_path = tmp_path / "circuit_breaker.json"
    history_path = tmp_path / "circuit_breaker_history.jsonl"

    # Start FULL with peak 100; observe equity 91 → DD = 9% → should flip to HALF
    pr.save_state(pr.CircuitBreakerState(
        last_observed_equity=100.0, peak_equity=100.0, state="FULL",
        updated_at="2026-01-01T00:00:00+00:00",
    ), path=state_path, history_path=history_path)

    pr.advance(
        observed_equity=91.0,
        thresholds=pr.CircuitBreakerThresholds(),
        state_path=state_path,
        history_path=history_path,
    )

    assert history_path.exists()
    rows = [json.loads(line) for line in history_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["from_state"] == "FULL"
    assert row["to_state"] == "HALF"
    assert "timestamp" in row
    assert abs(row["dd_pct"] - 9.0) < 0.01
    assert abs(row["observed_equity"] - 91.0) < 0.01
    assert abs(row["peak_equity"] - 100.0) < 0.01


def test_advance_does_not_append_history_when_state_unchanged(tmp_path):
    """Steady FULL → FULL must not write to history."""
    from lib import portfolio_risk as pr

    state_path = tmp_path / "circuit_breaker.json"
    history_path = tmp_path / "circuit_breaker_history.jsonl"

    pr.save_state(pr.CircuitBreakerState(
        last_observed_equity=100.0, peak_equity=100.0, state="FULL",
        updated_at="2026-01-01T00:00:00+00:00",
    ), path=state_path, history_path=history_path)

    pr.advance(
        observed_equity=99.5,  # tiny dip, still FULL
        thresholds=pr.CircuitBreakerThresholds(),
        state_path=state_path,
        history_path=history_path,
    )

    assert not history_path.exists() or history_path.read_text().strip() == ""
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_portfolio_risk.py -v -k "history"
```
Expected: TypeError because `save_state` and `advance` don't accept `history_path` yet.

- [ ] **Step 4: Implement the history append**

In `lib/portfolio_risk.py`:

1. Add a module-level `HISTORY_PATH` constant near `STATE_PATH`:
   ```python
   HISTORY_PATH = REPO_ROOT / "trades" / "paper" / "circuit_breaker_history.jsonl"
   ```
2. Add `history_path: Path | None = None` to `save_state()` — accept and ignore for backward compat (it's the state-snapshot writer; the history append happens in `advance`). Actually: just leave `save_state` alone, only modify `advance`.
3. Modify `advance()` signature:
   ```python
   def advance(
       observed_equity: float,
       *,
       thresholds: CircuitBreakerThresholds | None = None,
       state_path: Path | None = None,
       history_path: Path | None = None,
   ) -> CircuitBreakerStep:
   ```
4. After computing `new_step` and before `save_state(...)`, add:
   ```python
   if new_step.from_state != new_step.to_state:
       hist = history_path or HISTORY_PATH
       hist.parent.mkdir(parents=True, exist_ok=True)
       record = {
           "timestamp": new_step.updated_at,
           "from_state": new_step.from_state,
           "to_state": new_step.to_state,
           "dd_pct": new_step.dd_pct,
           "observed_equity": observed_equity,
           "peak_equity": new_step.peak_equity,
       }
       with hist.open("a", encoding="utf-8") as f:
           f.write(json.dumps(record) + "\n")
   ```
   (Adapt field names to whatever the existing `CircuitBreakerStep` dataclass uses — read the file first.)

- [ ] **Step 5: Run the new tests + the full suite**

```bash
python3 -m pytest tests/ -v
```
Expected: 2 new tests pass; all previously-passing tests still pass.

- [ ] **Step 6: Add `circuit_breaker_history.jsonl` to the append-only hook**

Read `.claude/hooks/append_only.sh` to confirm it matches a regex. The existing matcher already covers `trades/paper/log.csv` and `decisions/by_symbol/*.md`. Extend the file regex (in `.claude/settings.json` under hook #12 matcher) to include `trades/paper/circuit_breaker_history\.jsonl`.

```bash
grep -n "append_only\|circuit_breaker" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/.claude/settings.json
```

Edit the matcher pattern. The hook script itself shouldn't need changes (it already verifies "new content is a strict append").

- [ ] **Step 7: Commit**

```bash
git add lib/portfolio_risk.py tests/test_portfolio_risk.py .claude/settings.json
git commit -m "feat(portfolio_risk): append transitions to circuit_breaker_history.jsonl

The live-trading-gate helper needs an audit trail of historical
state transitions to verify the system has survived stress events.
advance() now writes a JSONL row whenever state changes; no-op
ticks don't pollute the log. File is append-only via hook #12.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Add `regime_diversity_gates` to risk_limits.yaml + schema

**Files:**
- Modify: `config/risk_limits.yaml`
- Modify: `tests/schemas/risk_limits.schema.json`

This is a config-only change (PR-required per CLAUDE.md, but the actual edit is small and reviewable). Add a sub-block under `gates:` describing what's required *in addition* to the existing days/trades/Sharpe/DD floor.

- [ ] **Step 1: Read the current `gates:` block**

```bash
sed -n '32,45p' /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/config/risk_limits.yaml
```
Expected: existing fields `require_human_approval_for_live_trades`, `minimum_paper_trading_days_before_live`, `minimum_paper_trades_before_live`.

- [ ] **Step 2: Add the new sub-block to `config/risk_limits.yaml`**

Use Edit to insert under the existing `gates:` block (preserve indentation):

```yaml
  # Regime-diversity gates: paper-trading evidence must demonstrate the system
  # has survived at least one stress event before live unlock is permitted.
  # All flags must evaluate true for the monthly_review routine to recommend
  # PROPOSE_HUMAN_APPROVED_LIVE.
  regime_diversity_gates:
    enabled: true
    # At least one circuit-breaker transition (FULL→HALF or worse) must have
    # occurred in paper-trading history. Proves the breaker actually engages.
    require_cb_throttle_event: true
    # At least one full SPY 10-month-SMA trend flip (above→below or below→above)
    # must have occurred during the paper-trading window. Proves the trend
    # filter actually flipped state, not just held one regime the whole time.
    require_spy_trend_flip: true
    # At least one observed daily VIX close ≥ this level during the window.
    # 25 is "elevated" — not a panic, just non-benign volatility.
    require_vix_high_observed: 25.0
    # Minimum number of distinct calendar months in the paper-trading window
    # (must be ≥ 4 for any seasonal evidence to mean anything).
    minimum_distinct_months: 4
```

- [ ] **Step 3: Extend the schema**

Read `tests/schemas/risk_limits.schema.json` at the `"gates"` block. Add `regime_diversity_gates` to its `properties` and to its `required` array:

```json
"regime_diversity_gates": {
  "type": "object",
  "additionalProperties": false,
  "required": [
    "enabled",
    "require_cb_throttle_event",
    "require_spy_trend_flip",
    "require_vix_high_observed",
    "minimum_distinct_months"
  ],
  "properties": {
    "enabled": { "type": "boolean" },
    "require_cb_throttle_event": { "type": "boolean" },
    "require_spy_trend_flip": { "type": "boolean" },
    "require_vix_high_observed": { "type": "number", "exclusiveMinimum": 0 },
    "minimum_distinct_months": { "type": "integer", "minimum": 1 }
  }
}
```

Add `"regime_diversity_gates"` to the `gates.required` array.

- [ ] **Step 4: Run schema validation**

```bash
python3 tests/run_schema_validation.py
```
Expected: PASS for all configs.

- [ ] **Step 5: Run the full test suite**

```bash
python3 -m pytest tests/ -v
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add config/risk_limits.yaml tests/schemas/risk_limits.schema.json
git commit -m "feat(risk): add regime_diversity_gates to live-trading unlock criteria

Adds four conditions that must hold in addition to the existing
days/trades/Sharpe/DD floors before monthly_review may recommend
PROPOSE_HUMAN_APPROVED_LIVE:
  - At least one CB throttle event observed
  - At least one SPY 10-mo-SMA trend flip during the window
  - At least one VIX close ≥ 25
  - At least 4 distinct calendar months of operation

Schema extended; existing tests still pass.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Implement the gate-evaluator helper

**Files:**
- Create: `lib/live_trading_gate.py`
- Create: `tests/test_live_trading_gate.py`

A pure helper that takes file paths (or pre-loaded data structures) and returns a structured verdict. The monthly_review routine calls this and surfaces the result.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_live_trading_gate.py
"""Tests for the live-trading gate evaluator.

All tests use synthetic inputs (no real CB history, no real bars).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.live_trading_gate import (  # noqa: E402
    GateConfig, GateInputs, evaluate_gates, has_cb_throttle_event,
    has_spy_trend_flip, has_vix_high_observed, distinct_calendar_months,
)


def _config(**overrides):
    base = dict(
        enabled=True,
        minimum_paper_trading_days=90,
        minimum_paper_trades=30,
        minimum_sharpe=0.8,
        maximum_drawdown_pct=12.0,
        regime_diversity_enabled=True,
        require_cb_throttle_event=True,
        require_spy_trend_flip=True,
        require_vix_high_observed=25.0,
        minimum_distinct_months=4,
    )
    base.update(overrides)
    return GateConfig(**base)


def test_has_cb_throttle_event_true_when_history_has_full_to_half():
    history = [
        {"timestamp": "2026-02-01T12:00:00+00:00",
         "from_state": "FULL", "to_state": "HALF", "dd_pct": 8.5,
         "observed_equity": 91500.0, "peak_equity": 100000.0},
    ]
    assert has_cb_throttle_event(history) is True


def test_has_cb_throttle_event_false_on_empty_history():
    assert has_cb_throttle_event([]) is False


def test_has_cb_throttle_event_ignores_recovery_only():
    """A HALF→FULL recovery alone (with no preceding FULL→HALF) doesn't count."""
    history = [
        {"timestamp": "2026-03-01T12:00:00+00:00",
         "from_state": "HALF", "to_state": "FULL", "dd_pct": 4.0,
         "observed_equity": 96000.0, "peak_equity": 100000.0},
    ]
    # The current rule: any throttle event (FULL→HALF or HALF→OUT) counts.
    # Pure recoveries don't.
    assert has_cb_throttle_event(history) is False


def test_has_spy_trend_flip_true_when_filter_changed_state():
    """Daily snapshots showing SPY > 10mo SMA early then < 10mo SMA later."""
    snapshots = [
        {"date": "2026-01-15", "spy_above_10mo_sma": True},
        {"date": "2026-02-15", "spy_above_10mo_sma": True},
        {"date": "2026-03-15", "spy_above_10mo_sma": False},  # flip
        {"date": "2026-04-15", "spy_above_10mo_sma": False},
    ]
    assert has_spy_trend_flip(snapshots) is True


def test_has_spy_trend_flip_false_when_always_above():
    snapshots = [
        {"date": "2026-01-15", "spy_above_10mo_sma": True},
        {"date": "2026-02-15", "spy_above_10mo_sma": True},
        {"date": "2026-03-15", "spy_above_10mo_sma": True},
    ]
    assert has_spy_trend_flip(snapshots) is False


def test_has_vix_high_observed_true_when_any_close_at_or_above_threshold():
    snapshots = [
        {"date": "2026-01-15", "vix_close": 18.0},
        {"date": "2026-02-15", "vix_close": 26.5},
        {"date": "2026-03-15", "vix_close": 19.0},
    ]
    assert has_vix_high_observed(snapshots, threshold=25.0) is True


def test_has_vix_high_observed_false_when_all_below():
    snapshots = [
        {"date": "2026-01-15", "vix_close": 14.0},
        {"date": "2026-02-15", "vix_close": 22.0},
    ]
    assert has_vix_high_observed(snapshots, threshold=25.0) is False


def test_distinct_calendar_months():
    snapshots = [
        {"date": "2026-01-15"}, {"date": "2026-01-28"},
        {"date": "2026-02-03"}, {"date": "2026-04-19"},
    ]
    assert distinct_calendar_months(snapshots) == 3  # Jan, Feb, Apr


def test_evaluate_gates_all_pass():
    cfg = _config()
    inputs = GateInputs(
        paper_trading_days=120,
        closed_paper_trades=45,
        portfolio_sharpe=1.05,
        portfolio_max_drawdown_pct=10.5,
        cb_history=[
            {"timestamp": "2026-02-01T12:00:00+00:00", "from_state": "FULL",
             "to_state": "HALF", "dd_pct": 8.5,
             "observed_equity": 91500.0, "peak_equity": 100000.0},
        ],
        daily_snapshots=[
            {"date": "2026-01-15", "spy_above_10mo_sma": True, "vix_close": 18.0},
            {"date": "2026-02-15", "spy_above_10mo_sma": False, "vix_close": 27.0},
            {"date": "2026-03-15", "spy_above_10mo_sma": False, "vix_close": 22.0},
            {"date": "2026-04-15", "spy_above_10mo_sma": False, "vix_close": 20.0},
        ],
    )
    verdict = evaluate_gates(cfg, inputs)
    assert verdict.overall_pass is True
    assert all(g.passed for g in verdict.gates)


def test_evaluate_gates_fails_on_missing_cb_event():
    cfg = _config()
    inputs = GateInputs(
        paper_trading_days=120,
        closed_paper_trades=45,
        portfolio_sharpe=1.05,
        portfolio_max_drawdown_pct=10.5,
        cb_history=[],  # no throttle ever fired
        daily_snapshots=[
            {"date": f"2026-{m:02}-15", "spy_above_10mo_sma": (m % 2 == 0),
             "vix_close": 27.0 if m == 2 else 18.0}
            for m in range(1, 6)
        ],
    )
    verdict = evaluate_gates(cfg, inputs)
    assert verdict.overall_pass is False
    failures = [g.name for g in verdict.gates if not g.passed]
    assert "cb_throttle_event" in failures


def test_evaluate_gates_disabled_returns_pass_with_warning():
    cfg = _config(enabled=False)
    inputs = GateInputs(
        paper_trading_days=10, closed_paper_trades=2,
        portfolio_sharpe=0.1, portfolio_max_drawdown_pct=20.0,
        cb_history=[], daily_snapshots=[],
    )
    verdict = evaluate_gates(cfg, inputs)
    assert verdict.overall_pass is True
    assert verdict.warning is not None
    assert "disabled" in verdict.warning.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_live_trading_gate.py -v
```
Expected: `ModuleNotFoundError: No module named 'lib.live_trading_gate'`.

- [ ] **Step 3: Implement `lib/live_trading_gate.py`**

```python
# lib/live_trading_gate.py
"""Live-trading unlock gate evaluator.

Pure functions over already-loaded inputs. Reading the underlying files
(circuit_breaker_history.jsonl, paper log, daily snapshots, config) is
the caller's responsibility — see `load_default_inputs()` for the
production assembly used by the monthly_review routine.

Used only by the monthly_review routine. The gate verdict is a
RECOMMENDATION input, not a permission system: human approval is still
required, and CLAUDE.md still locks live execution behind explicit PR.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class GateConfig:
    enabled: bool
    minimum_paper_trading_days: int
    minimum_paper_trades: int
    minimum_sharpe: float
    maximum_drawdown_pct: float
    regime_diversity_enabled: bool
    require_cb_throttle_event: bool
    require_spy_trend_flip: bool
    require_vix_high_observed: float  # threshold; e.g. 25.0
    minimum_distinct_months: int


@dataclass
class GateInputs:
    paper_trading_days: int
    closed_paper_trades: int
    portfolio_sharpe: float
    portfolio_max_drawdown_pct: float
    cb_history: list[dict]              # rows from circuit_breaker_history.jsonl
    daily_snapshots: list[dict]         # rows from memory/daily_snapshots/*.md (parsed)


@dataclass
class GateResult:
    name: str
    passed: bool
    actual: Any
    required: Any
    note: str = ""


@dataclass
class GateVerdict:
    overall_pass: bool
    gates: list[GateResult] = field(default_factory=list)
    warning: str | None = None  # set when disabled / when inputs are sparse


# -- Individual gate predicates -------------------------------------------

THROTTLE_TRANSITIONS = {("FULL", "HALF"), ("HALF", "OUT"), ("FULL", "OUT")}


def has_cb_throttle_event(cb_history: list[dict]) -> bool:
    """At least one FULL→HALF, HALF→OUT, or FULL→OUT transition observed."""
    return any(
        (row.get("from_state"), row.get("to_state")) in THROTTLE_TRANSITIONS
        for row in cb_history
    )


def has_spy_trend_flip(snapshots: list[dict]) -> bool:
    """At least one change in `spy_above_10mo_sma` across the snapshot history."""
    states = [s.get("spy_above_10mo_sma") for s in snapshots
              if s.get("spy_above_10mo_sma") is not None]
    return len(set(states)) >= 2


def has_vix_high_observed(snapshots: list[dict], *, threshold: float) -> bool:
    """At least one daily VIX close at or above `threshold`."""
    return any(
        (s.get("vix_close") is not None) and (s["vix_close"] >= threshold)
        for s in snapshots
    )


def distinct_calendar_months(snapshots: list[dict]) -> int:
    """Number of distinct YYYY-MM keys present in snapshots."""
    months = set()
    for s in snapshots:
        d = s.get("date")
        if d and len(d) >= 7:
            months.add(d[:7])
    return len(months)


# -- Top-level evaluator --------------------------------------------------


def evaluate_gates(config: GateConfig, inputs: GateInputs) -> GateVerdict:
    """Evaluate every gate and return a structured verdict.

    If `config.enabled` is False, returns overall_pass=True with a warning
    so the routine can surface that gates were bypassed by config.
    """
    if not config.enabled:
        return GateVerdict(
            overall_pass=True,
            gates=[],
            warning="Live-trading gates are disabled in config (gates.enabled=false)",
        )

    results: list[GateResult] = []

    # Existing floors
    results.append(GateResult(
        name="paper_trading_days",
        passed=inputs.paper_trading_days >= config.minimum_paper_trading_days,
        actual=inputs.paper_trading_days,
        required=config.minimum_paper_trading_days,
    ))
    results.append(GateResult(
        name="closed_paper_trades",
        passed=inputs.closed_paper_trades >= config.minimum_paper_trades,
        actual=inputs.closed_paper_trades,
        required=config.minimum_paper_trades,
    ))
    results.append(GateResult(
        name="portfolio_sharpe",
        passed=inputs.portfolio_sharpe >= config.minimum_sharpe,
        actual=round(inputs.portfolio_sharpe, 3),
        required=config.minimum_sharpe,
    ))
    results.append(GateResult(
        name="portfolio_max_drawdown",
        passed=inputs.portfolio_max_drawdown_pct <= config.maximum_drawdown_pct,
        actual=round(inputs.portfolio_max_drawdown_pct, 2),
        required=f"≤ {config.maximum_drawdown_pct}",
    ))

    # Regime-diversity gates
    if config.regime_diversity_enabled:
        if config.require_cb_throttle_event:
            ok = has_cb_throttle_event(inputs.cb_history)
            results.append(GateResult(
                name="cb_throttle_event",
                passed=ok,
                actual=len(inputs.cb_history),
                required="≥ 1 FULL→HALF or HALF→OUT transition",
                note="From trades/paper/circuit_breaker_history.jsonl",
            ))
        if config.require_spy_trend_flip:
            ok = has_spy_trend_flip(inputs.daily_snapshots)
            results.append(GateResult(
                name="spy_trend_flip",
                passed=ok,
                actual="observed" if ok else "no flip",
                required="At least one SPY 10mo-SMA filter change in window",
                note="From memory/daily_snapshots/<date>.md",
            ))
        if config.require_vix_high_observed > 0:
            ok = has_vix_high_observed(inputs.daily_snapshots,
                                       threshold=config.require_vix_high_observed)
            results.append(GateResult(
                name="vix_high_observed",
                passed=ok,
                actual=max((s.get("vix_close") or 0) for s in inputs.daily_snapshots) if inputs.daily_snapshots else 0,
                required=f"≥ {config.require_vix_high_observed}",
            ))
        n_months = distinct_calendar_months(inputs.daily_snapshots)
        results.append(GateResult(
            name="distinct_calendar_months",
            passed=n_months >= config.minimum_distinct_months,
            actual=n_months,
            required=config.minimum_distinct_months,
        ))

    overall = all(g.passed for g in results)
    return GateVerdict(overall_pass=overall, gates=results)


# -- Production input loader (consumed by monthly_review prompt) ---------


def load_default_inputs(*, performance_summary: dict) -> GateInputs:
    """Load gate inputs from canonical paths.

    `performance_summary` is supplied by the performance_review subagent and
    must contain: paper_trading_days, closed_paper_trades, portfolio_sharpe,
    portfolio_max_drawdown_pct.
    """
    history_path = REPO_ROOT / "trades" / "paper" / "circuit_breaker_history.jsonl"
    cb_history: list[dict] = []
    if history_path.exists():
        for line in history_path.read_text().splitlines():
            line = line.strip()
            if line:
                cb_history.append(json.loads(line))

    snapshots_dir = REPO_ROOT / "memory" / "daily_snapshots"
    daily_snapshots: list[dict] = []
    if snapshots_dir.exists():
        for snap_path in sorted(snapshots_dir.glob("*.md")):
            parsed = _parse_snapshot(snap_path)
            if parsed:
                daily_snapshots.append(parsed)

    return GateInputs(
        paper_trading_days=performance_summary["paper_trading_days"],
        closed_paper_trades=performance_summary["closed_paper_trades"],
        portfolio_sharpe=performance_summary["portfolio_sharpe"],
        portfolio_max_drawdown_pct=performance_summary["portfolio_max_drawdown_pct"],
        cb_history=cb_history,
        daily_snapshots=daily_snapshots,
    )


def _parse_snapshot(path: Path) -> dict | None:
    """Parse a daily snapshot for the fields we care about.

    Snapshots are markdown with a known structure; we extract just the
    date, spy_above_10mo_sma, and vix_close fields if present. Missing
    fields are tolerated (recorded as None).
    """
    text = path.read_text(encoding="utf-8")
    out: dict = {"date": path.stem, "spy_above_10mo_sma": None, "vix_close": None}
    for line in text.splitlines():
        # Conventional snapshot markers (extend as the snapshot format evolves):
        # `- spy_above_10mo_sma: true`
        # `- vix_close: 22.4`
        s = line.strip().lstrip("-* ").strip()
        if s.startswith("spy_above_10mo_sma:"):
            v = s.split(":", 1)[1].strip().lower()
            out["spy_above_10mo_sma"] = v in ("true", "yes", "1")
        elif s.startswith("vix_close:"):
            try:
                out["vix_close"] = float(s.split(":", 1)[1].strip())
            except ValueError:
                pass
    return out
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_live_trading_gate.py -v
```
Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/live_trading_gate.py tests/test_live_trading_gate.py
git commit -m "feat: live-trading gate evaluator (pure helpers + structured verdict)

Reads circuit_breaker_history.jsonl + daily snapshots + perf summary,
returns a GateVerdict with per-gate pass/fail + actual vs required.
Consumed by the monthly_review routine.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Extend daily snapshots to record SPY-above-SMA and VIX

**Files:**
- Modify: `lib/snapshots.py`
- Modify: `tests/test_snapshots.py`
- Modify: `prompts/routines/end_of_day.md`

The gate needs `spy_above_10mo_sma` and `vix_close` in each daily snapshot. They aren't currently captured. This is an additive change.

- [ ] **Step 1: Read the current snapshot writer**

```bash
grep -n "def\|spy\|vix\|sma" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/lib/snapshots.py | head -30
```
Expected: locate the snapshot-construction function and its kwargs.

- [ ] **Step 2: Write the failing test**

In `tests/test_snapshots.py`, add (adapt to whatever the existing API looks like):

```python
def test_snapshot_includes_spy_trend_and_vix_when_provided(tmp_path):
    from lib import snapshots
    out = snapshots.write_snapshot(
        date_iso="2026-05-12",
        regime="bullish_trend",
        cb_state="FULL",
        pnl_dollars=42.0,
        decisions_summary="3 NO_TRADE, 1 PAPER_BUY",
        open_positions_summary="GLD 10%, SPY 50%",
        notable="-",
        watch_tomorrow="-",
        spy_above_10mo_sma=False,   # NEW
        vix_close=27.4,             # NEW
        snapshots_dir=tmp_path,
    )
    body = out.read_text()
    assert "spy_above_10mo_sma: false" in body.lower()
    assert "vix_close: 27.4" in body


def test_snapshot_omits_spy_trend_and_vix_when_not_provided(tmp_path):
    from lib import snapshots
    out = snapshots.write_snapshot(
        date_iso="2026-05-12",
        regime="bullish_trend",
        cb_state="FULL",
        pnl_dollars=42.0,
        decisions_summary="3 NO_TRADE",
        open_positions_summary="GLD 10%",
        notable="-",
        watch_tomorrow="-",
        snapshots_dir=tmp_path,
    )
    body = out.read_text()
    # Optional fields should simply be absent, not emitted as null
    assert "spy_above_10mo_sma" not in body
    assert "vix_close" not in body
```

- [ ] **Step 3: Run test to see it fail**

```bash
python3 -m pytest tests/test_snapshots.py -v -k "spy_trend_and_vix"
```
Expected: TypeError or AttributeError (parameters don't exist).

- [ ] **Step 4: Add the two optional kwargs to `write_snapshot()`**

In `lib/snapshots.py`, add `spy_above_10mo_sma: bool | None = None, vix_close: float | None = None` to the function signature. In the markdown body construction, conditionally append:

```python
if spy_above_10mo_sma is not None:
    lines.append(f"- spy_above_10mo_sma: {'true' if spy_above_10mo_sma else 'false'}")
if vix_close is not None:
    lines.append(f"- vix_close: {vix_close:.1f}")
```

- [ ] **Step 5: Run all snapshot tests + the full suite**

```bash
python3 -m pytest tests/ -v
```
Expected: all green.

- [ ] **Step 6: Update the `end_of_day` prompt to populate the two new fields**

Read `prompts/routines/end_of_day.md`, find the snapshot-write step (search for `write_snapshot` or `snapshots.py`). Update the call to compute and pass:
- `spy_above_10mo_sma` — from the closing SPY price vs the 10-month SMA computed in the same routine (the routine already runs Strategy A, which uses this value).
- `vix_close` — fetch from market data (Alpaca quote for `^VIX` if available, or the `VIX` CBOE feed; document the source in the prompt).

If VIX is not available from the broker, document that clearly: the prompt should set `vix_close=None` and the gate will treat the field as absent. The `vix_high_observed` gate check will then fail until a data source is wired — which is intentional pressure to add it before going live.

- [ ] **Step 7: Commit**

```bash
git add lib/snapshots.py tests/test_snapshots.py prompts/routines/end_of_day.md
git commit -m "feat(snapshots): record spy_above_10mo_sma and vix_close in daily snapshots

Live-trading gate consumes these fields to verify the system has seen
both trend regimes and at least one elevated-VIX day before unlock.
Both fields optional and additive — old snapshots remain valid.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Wire the gate into `monthly_review.md`

**Files:**
- Modify: `prompts/routines/monthly_review.md`

The monthly review is where the recommendation (`STAY_PAPER` / `PROPOSE_HUMAN_APPROVED_LIVE` / `HALT_AND_REVIEW`) is produced. It must call the gate evaluator and use the verdict in its decision logic.

- [ ] **Step 1: Read the current monthly_review prompt**

```bash
cat /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/prompts/routines/monthly_review.md
```
Expected: Confirm where the recommendation logic sits (currently around step 5 in the numbered list).

- [ ] **Step 2: Add a new step "Live-trading gate check" to `prompts/routines/monthly_review.md`**

Use Edit to insert a new step between the existing performance_review step and the recommendation step:

```markdown
5a. **Live-trading gate evaluation** (before any recommendation):

```python
python3 - <<'PYGATE'
from lib import config, live_trading_gate as gate

risk = config.risk_limits()
g = risk["gates"]
rd = g["regime_diversity_gates"]

cfg = gate.GateConfig(
    enabled=True,                    # CLAUDE.md / risk_limits gates always enabled in v1
    minimum_paper_trading_days=g["minimum_paper_trading_days_before_live"],
    minimum_paper_trades=g["minimum_paper_trades_before_live"],
    minimum_sharpe=0.8,              # from CLAUDE.md
    maximum_drawdown_pct=12.0,       # from CLAUDE.md (12% softer cap, before 15% hard cap)
    regime_diversity_enabled=rd["enabled"],
    require_cb_throttle_event=rd["require_cb_throttle_event"],
    require_spy_trend_flip=rd["require_spy_trend_flip"],
    require_vix_high_observed=rd["require_vix_high_observed"],
    minimum_distinct_months=rd["minimum_distinct_months"],
)

# `perf_summary` must be provided by the performance_review step above; pass it
# in via JSON file or environment depending on the routine's I/O convention.
import json, sys
perf_summary = json.loads(sys.stdin.read())

inputs = gate.load_default_inputs(performance_summary=perf_summary)
verdict = gate.evaluate_gates(cfg, inputs)
print(json.dumps({
    "overall_pass": verdict.overall_pass,
    "warning": verdict.warning,
    "gates": [{"name": g.name, "passed": g.passed, "actual": g.actual,
               "required": g.required, "note": g.note} for g in verdict.gates],
}, indent=2))
PYGATE
```

Save the verdict JSON to `reports/learning/monthly_review_<YYYY-MM>_gate_verdict.json` for the audit trail.

5b. **Recommendation decision** (REPLACES the existing recommendation logic):

- If `verdict.overall_pass` is **True** AND `verdict.warning` is None AND no halt triggers fired → may recommend `PROPOSE_HUMAN_APPROVED_LIVE`. (The recommendation is still subject to the existing "never advance more than one mode-step at a time" constraint — from PAPER_TRADING the next legal step is LIVE_PROPOSALS, NOT LIVE_EXECUTION.)
- If `verdict.overall_pass` is **False** → recommend `STAY_PAPER`. List the failing gates by name in the recommendation rationale.
- If any halt trigger from CLAUDE.md is hit → recommend `HALT_AND_REVIEW` regardless of gate verdict.
```

Update the existing `## Composing the Telegram notification` section to add a bullet:

```
• *Gate verdict:* <overall_pass> (failing: <comma-separated names or "—">)
```

- [ ] **Step 3: Smoke-test the helper end-to-end with a synthetic perf_summary**

```bash
echo '{"paper_trading_days": 5, "closed_paper_trades": 0, "portfolio_sharpe": 0.0, "portfolio_max_drawdown_pct": 0.5}' | python3 -c "
import json, sys
from lib import live_trading_gate as gate
perf = json.loads(sys.stdin.read())
cfg = gate.GateConfig(
    enabled=True, minimum_paper_trading_days=90, minimum_paper_trades=30,
    minimum_sharpe=0.8, maximum_drawdown_pct=12.0,
    regime_diversity_enabled=True, require_cb_throttle_event=True,
    require_spy_trend_flip=True, require_vix_high_observed=25.0,
    minimum_distinct_months=4,
)
inputs = gate.load_default_inputs(performance_summary=perf)
verdict = gate.evaluate_gates(cfg, inputs)
print('overall_pass:', verdict.overall_pass)
for g in verdict.gates:
    print(f'  {g.name}: {\"PASS\" if g.passed else \"FAIL\"} (actual={g.actual}, required={g.required})')
"
```
Expected: `overall_pass: False` (we have ~1 day of paper history). Several gates listed as FAIL with actual/required visible.

- [ ] **Step 4: Commit**

```bash
git add prompts/routines/monthly_review.md
git commit -m "feat(monthly_review): wire live-trading gate verdict into recommendation

The recommendation (STAY_PAPER / PROPOSE_HUMAN_APPROVED_LIVE /
HALT_AND_REVIEW) now requires the live_trading_gate verdict to pass
before PROPOSE_HUMAN_APPROVED_LIVE is permitted. Gate verdict is
saved to reports/learning/ for audit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Update CLAUDE.md unlock-criteria block

**Files:**
- Modify: `CLAUDE.md` (around line 157)

The narrative criteria in CLAUDE.md must reflect what's now enforced by the gate.

- [ ] **Step 1: Read the current block**

```bash
sed -n '155,165p' /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/CLAUDE.md
```

- [ ] **Step 2: Replace the block via Edit**

Find the existing block:
```
**Live-trading unlock criteria (not active in v1):**
- 90+ trading days of paper operation.
- 30+ closed paper trades across all strategies.
- Portfolio Sharpe ratio ≥ 0.8 on paper data.
- Max drawdown ≤ 12% on paper data.
- Explicit human PR + signed update to `docs/risk_profile.md`.
```

Replace with:
```
**Live-trading unlock criteria (not active in v1):**

*Floor criteria (existing):*
- 90+ trading days of paper operation.
- 30+ closed paper trades across all strategies.
- Portfolio Sharpe ratio ≥ 0.8 on paper data.
- Max drawdown ≤ 12% on paper data.
- Explicit human PR + signed update to `docs/risk_profile.md`.

*Regime-diversity criteria (added 2026-05-12):* the system must have *survived* at least one stress event in paper, not just operated in benign conditions.
- At least one circuit-breaker throttle event observed (FULL→HALF or HALF→OUT).
- At least one SPY 10-month-SMA trend flip during the window (proves the trend filter actually changed state).
- At least one daily VIX close ≥ 25 observed (proves the system has seen elevated volatility).
- At least 4 distinct calendar months of operation (any one month, however good, is uninformative).

These criteria are evaluated by `lib.live_trading_gate.evaluate_gates()` during the monthly review routine and surfaced in its recommendation. The verdict is a recommendation input only — human PR approval remains required.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE): tighten live-trading unlock criteria with regime diversity

Adds four regime-diversity gates: must observe a CB throttle event,
a SPY 10mo-SMA trend flip, a VIX ≥ 25 day, and ≥ 4 distinct months
before monthly_review may recommend PROPOSE_HUMAN_APPROVED_LIVE.

The reviewer's concern: 90 days + 30 trades + Sharpe + DD can all be
satisfied by a benign trending stretch. Stress-evidence is now required.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

1. **Spec coverage:** Three layers — config (Task 2), helper (Task 3), prompt wiring (Task 5), CLAUDE.md (Task 6). Plus the supporting CB-history (Task 1) and snapshot fields (Task 4). All five regime gates present. ✓
2. **Placeholders:** None. Every step has runnable code or a concrete edit.
3. **Type consistency:** `GateConfig`, `GateInputs`, `GateResult`, `GateVerdict` defined in Task 3 and consumed in Task 5. Field names stable across all uses.
4. **Hook compatibility:** `risk_limits.yaml` edit is schema-validated by hook #2. `CLAUDE.md` is not a config file and has no hook gating. `prompts/routines/*.md` is locked by hook #5 — Task 5 must go through `prompts/proposed_updates/` + PR. **Add this note for the executor**: do not edit `prompts/routines/monthly_review.md` directly; write the proposed update at `prompts/proposed_updates/2026-05-12_monthly_review_live_gate.md` and require a human PR.

## Stopping Conditions

- If hook #5 blocks the direct edit in Task 5, the plan is correctly enforcing repo policy. Switch to writing the proposed update under `prompts/proposed_updates/` and surface to the user that a human PR is required.
- If the snapshot-parse helper (`_parse_snapshot` in Task 3) cannot find any `spy_above_10mo_sma` or `vix_close` fields in existing snapshots, the gate will fail until at least one fresh snapshot is written. This is by design but worth surfacing on the first run.
