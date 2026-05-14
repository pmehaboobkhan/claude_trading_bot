# Walk-Forward + Parameter Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that the chosen circuit-breaker thresholds (5%/8% asymmetric) and Strategy A SMA window (10-month) are robust — not isolated parameter wins from in-sample search.

**Architecture:** Two new offline scripts, both reusing the existing `scripts/run_multi_strategy_backtest.py` machinery in-process (no subprocess). One sweeps circuit-breaker thresholds across the full window and writes a stability matrix. The other does a true walk-forward: pick best CB thresholds on a rolling 5-year IS window, evaluate on the next 1-year OOS window, repeat across the full history. Both write reports to `reports/learning/` and never touch production code, prompts, or configs.

**Tech Stack:** Python 3.12, existing `lib.backtest`, `lib.signals`, `lib.portfolio_risk`, yfinance cache at `backtests/_yfinance_cache/`. Pure stdlib + already-installed deps.

---

## Why this matters (one paragraph for the executor)

The 5%/8%/8%/12% breaker thresholds were chosen on a single 13-year window. If neighboring choices (4%/7%/7%/11%, 6%/9%/9%/13%, etc.) produce wildly different CAGR/DD/Sharpe, the chosen point is overfit and forward results will disappoint. We want a **plateau**, not a peak. Same logic for Strategy A's 10-month SMA — if 9 and 11 work and 10 is a spike, that's a different (worse) story than 8/9/10/11/12 all sitting in the same return/DD band.

---

## File Structure

**Create:**
- `scripts/run_cb_threshold_stability.py` — sweep the 4 CB thresholds across a parameter grid, write a stability matrix to `reports/learning/`.
- `scripts/run_sma_stability.py` — sweep Strategy A's monthly SMA window (8, 9, 10, 11, 12 months), write a comparison.
- `scripts/run_walk_forward.py` — true walk-forward over CB thresholds: rolling 5-year IS optimization, 1-year OOS evaluation.
- `tests/test_walk_forward.py` — unit tests for the WF window slicer + the OOS metric aggregator. Pure functions only; no network.

**Modify:**
- `scripts/run_multi_strategy_backtest.py` — extract the `main()` body into a callable `run_backtest(args_namespace) -> dict` so the new scripts can drive it in-process. **No behavior change** for existing CLI users.

**No edits to:**
- Any `config/*.yaml`
- Any `prompts/`
- Any `lib/portfolio_risk.py` logic (we only consume it)
- The chosen production thresholds

---

## Task 1: Refactor backtest entrypoint to be importable

**Files:**
- Modify: `scripts/run_multi_strategy_backtest.py` (extract `main()` body)
- Test: `tests/test_multi_strategy_backtest_entry.py` (new)

The current `main()` parses argv and runs end-to-end. We need a callable that takes a parsed `argparse.Namespace` (or equivalent dict) and returns the metrics dict, so sweep scripts can call it 50+ times in one process without subprocess overhead and without re-fetching yfinance bars.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_multi_strategy_backtest_entry.py
"""Verify run_multi_strategy_backtest.run_backtest() is callable in-process."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_multi_strategy_backtest as mod  # noqa: E402


def _default_args(**overrides):
    base = dict(
        start="2020-01-01",
        end="2021-12-31",
        capital=100_000.0,
        alloc_a=0.60, alloc_b=0.30, alloc_c=0.10,
        cash_buffer_pct=0.0,
        circuit_breaker=True,
        cb_half_dd=0.08, cb_out_dd=0.12,
        cb_recovery_dd=0.05, cb_out_recover_dd=0.08,
        label="test",
        write_report=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_run_backtest_returns_metrics_dict():
    """Sanity: callable form returns the expected metric keys."""
    result = mod.run_backtest(_default_args())
    assert isinstance(result, dict)
    for key in ("ann_return", "max_drawdown_pct", "sharpe", "final_equity",
                "cb_events", "n_trades"):
        assert key in result, f"missing key: {key}"
    # Sanity ranges (loose; just verifying we got real numbers)
    assert -100 < result["ann_return"] < 200
    assert 0 <= result["max_drawdown_pct"] <= 100


def test_run_backtest_no_report_when_write_report_false():
    """write_report=False must not create a file under backtests/."""
    args = _default_args(label="no_write_smoke")
    before = set((REPO_ROOT / "backtests" / "multi_strategy_portfolio").glob("*no_write_smoke*"))
    mod.run_backtest(args)
    after = set((REPO_ROOT / "backtests" / "multi_strategy_portfolio").glob("*no_write_smoke*"))
    assert before == after, "run_backtest wrote a report despite write_report=False"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_multi_strategy_backtest_entry.py -v
```
Expected: `AttributeError: module 'scripts.run_multi_strategy_backtest' has no attribute 'run_backtest'`

- [ ] **Step 3: Refactor `main()` into `run_backtest(args) -> dict` + thin `main()`**

In `scripts/run_multi_strategy_backtest.py`:
1. Add a `write_report=True` argument to the argparse parser:
   ```python
   parser.add_argument("--no-report", dest="write_report", action="store_false",
                       help="Skip writing the markdown report (used by sweep scripts)")
   parser.set_defaults(write_report=True)
   ```
2. Rename the body of `main()` (everything after `args = parser.parse_args()`) into a new function `run_backtest(args) -> dict`. The function must:
   - Accept any object with the same attributes as the parsed Namespace.
   - Return a dict with keys `ann_return`, `max_drawdown_pct`, `sharpe`, `final_equity`, `cb_events` (list), `n_trades` (int), `equity_curve` (list of (date, value)), `overall` (bool), `hit_low` (bool), `hit_high` (bool), `dd_ok` (bool), `sharpe_ok` (bool).
   - Skip the report-file write block when `getattr(args, "write_report", True)` is False.
   - Keep all printing — sweep scripts redirect/ignore stdout.
3. Restore `main()` to:
   ```python
   def main() -> int:
       parser = argparse.ArgumentParser()
       # ... all parser.add_argument calls ...
       args = parser.parse_args()
       result = run_backtest(args)
       return 0 if result["overall"] else 1
   ```

- [ ] **Step 4: Run all existing tests + the new one**

```bash
python3 -m pytest tests/ -v
```
Expected: All previously-passing tests still pass + the 2 new tests pass.

- [ ] **Step 5: Smoke-test the CLI for regression**

```bash
python3 scripts/run_multi_strategy_backtest.py --start 2020-01-01 --end 2021-12-31 --circuit-breaker --label refactor_smoke
```
Expected: Same output format as before; `backtests/multi_strategy_portfolio/2020-01-01_to_2021-12-31_refactor_smoke.md` exists.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_multi_strategy_backtest.py tests/test_multi_strategy_backtest_entry.py
git commit -m "refactor: extract run_backtest() entrypoint for in-process sweeps

Sweep scripts (walk-forward, threshold stability) need to drive the
backtest 50+ times per run. Subprocess overhead + yfinance refetch
made that unacceptable. CLI behavior unchanged.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Circuit-breaker threshold stability sweep

**Files:**
- Create: `scripts/run_cb_threshold_stability.py`
- Test: extend `tests/test_walk_forward.py` (created in Task 4) — but for this script, smoke-test only via execution.

This sweeps a small grid of CB thresholds over the *same* full historical window and writes a stability matrix. Purpose: show that 5%/8% is on a plateau, not a spike.

- [ ] **Step 1: Create the script**

```python
# scripts/run_cb_threshold_stability.py
"""Stability sweep over circuit-breaker thresholds.

Holds the strategies fixed (60/30/10 with IEF) and sweeps the four CB
thresholds across a small grid centered on the chosen production values
(half_dd=0.08, out_dd=0.12, half→full=0.05, out→half=0.08).

Output: reports/learning/cb_threshold_stability_<date>.md with a table
of (variant, CAGR, MaxDD, Sharpe, n_events) — one row per grid point.

Pass criterion (qualitative, no auto-pass/fail):
- Within ±1pp of each chosen threshold, CAGR should stay within ±1.5pp
  and MaxDD within ±2pp. If those bands are blown, the production point
  is on a peak, not a plateau, and the choice should be reviewed.

Usage:
    python scripts/run_cb_threshold_stability.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_multi_strategy_backtest as mod  # noqa: E402


# Grid: 5 values per axis, centered on the production choices.
# Total = 5 * 5 * 5 * 5 = 625, but we constrain to invariants
# (0 < half_dd < out_dd; recovery_dd < half_dd; out_recover_dd < out_dd).
# The constrained grid is ~80 valid combinations, each ~3-5s.
HALF_DD_GRID    = [0.06, 0.07, 0.08, 0.09, 0.10]
OUT_DD_GRID     = [0.10, 0.11, 0.12, 0.13, 0.14]
HALF_TO_FULL    = [0.03, 0.04, 0.05, 0.06, 0.07]
OUT_TO_HALF     = [0.06, 0.07, 0.08, 0.09, 0.10]


def valid_combo(h, o, htf, oth) -> bool:
    return (0 < h < o < 1) and (0 <= htf < h) and (htf <= oth < o)


def make_args(start, end, h, o, htf, oth):
    return SimpleNamespace(
        start=start, end=end,
        capital=100_000.0,
        alloc_a=0.60, alloc_b=0.30, alloc_c=0.10,
        cash_buffer_pct=0.0,
        circuit_breaker=True,
        cb_half_dd=h, cb_out_dd=o,
        cb_recovery_dd=htf, cb_out_recover_dd=oth,
        label="stability_sweep",
        write_report=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2013-05-24")
    parser.add_argument("--end", default="2026-05-08")
    args = parser.parse_args()

    combos = [
        (h, o, htf, oth)
        for h in HALF_DD_GRID
        for o in OUT_DD_GRID
        for htf in HALF_TO_FULL
        for oth in OUT_TO_HALF
        if valid_combo(h, o, htf, oth)
    ]
    print(f"[stability] {len(combos)} valid combinations over {args.start} → {args.end}")

    rows = []
    for i, (h, o, htf, oth) in enumerate(combos, 1):
        print(f"  [{i}/{len(combos)}] half={h:.2f} out={o:.2f} "
              f"h→f={htf:.2f} o→h={oth:.2f}")
        result = mod.run_backtest(make_args(args.start, args.end, h, o, htf, oth))
        rows.append({
            "half_dd": h, "out_dd": o, "h_to_f": htf, "o_to_h": oth,
            "cagr": result["ann_return"],
            "mdd": result["max_drawdown_pct"],
            "sharpe": result["sharpe"],
            "n_events": len(result["cb_events"]),
        })

    # Mark the production choice for visual reference.
    PROD = (0.08, 0.12, 0.05, 0.08)

    out_path = REPO_ROOT / "reports" / "learning" / (
        f"cb_threshold_stability_{datetime.utcnow():%Y-%m-%d}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Circuit-Breaker Threshold Stability Sweep — {datetime.utcnow():%Y-%m-%d}",
        "",
        f"Window: {args.start} → {args.end}",
        f"Strategies: 60/30/10 (TAA / large-cap / gold), IEF as Strategy A bond.",
        f"Total combinations evaluated: {len(rows)}",
        f"Production choice: half_dd=0.08, out_dd=0.12, h→f=0.05, o→h=0.08 (marked **PROD**).",
        "",
        "## All variants (sorted by Sharpe descending)",
        "",
        "| half_dd | out_dd | h→f | o→h | CAGR % | MaxDD % | Sharpe | events | tag |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in sorted(rows, key=lambda x: -x["sharpe"]):
        tag = " **PROD**" if (r["half_dd"], r["out_dd"], r["h_to_f"], r["o_to_h"]) == PROD else ""
        lines.append(
            f"| {r['half_dd']:.2f} | {r['out_dd']:.2f} | {r['h_to_f']:.2f} | "
            f"{r['o_to_h']:.2f} | {r['cagr']:+.2f} | {r['mdd']:.2f} | "
            f"{r['sharpe']:.2f} | {r['n_events']} |{tag} |"
        )

    # Plateau check around the production choice
    prod_row = next(r for r in rows if (r["half_dd"], r["out_dd"], r["h_to_f"], r["o_to_h"]) == PROD)
    neighbors = [r for r in rows
                 if abs(r["half_dd"] - PROD[0]) <= 0.01
                 and abs(r["out_dd"] - PROD[1]) <= 0.01
                 and abs(r["h_to_f"] - PROD[2]) <= 0.01
                 and abs(r["o_to_h"] - PROD[3]) <= 0.01
                 and (r["half_dd"], r["out_dd"], r["h_to_f"], r["o_to_h"]) != PROD]
    if neighbors:
        cagr_min = min(r["cagr"] for r in neighbors)
        cagr_max = max(r["cagr"] for r in neighbors)
        mdd_min = min(r["mdd"] for r in neighbors)
        mdd_max = max(r["mdd"] for r in neighbors)
        cagr_band = cagr_max - cagr_min
        mdd_band = mdd_max - mdd_min
        plateau = cagr_band <= 1.5 and mdd_band <= 2.0
        lines += [
            "",
            "## Plateau check (±1pp around production choice)",
            "",
            f"- Production CAGR: {prod_row['cagr']:+.2f}% / MaxDD: {prod_row['mdd']:.2f}% / Sharpe: {prod_row['sharpe']:.2f}",
            f"- Neighbor CAGR range: {cagr_min:+.2f}% to {cagr_max:+.2f}% (band {cagr_band:.2f}pp)",
            f"- Neighbor MaxDD range: {mdd_min:.2f}% to {mdd_max:.2f}% (band {mdd_band:.2f}pp)",
            f"- **Plateau verdict:** {'PASS — within ±1.5pp CAGR and ±2pp MaxDD bands' if plateau else 'FAIL — production choice may be overfit; review thresholds'}",
        ]

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[stability] wrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the sweep on a short window first to verify it works**

```bash
python3 scripts/run_cb_threshold_stability.py --start 2020-01-01 --end 2022-12-31
```
Expected: ~80 lines of `[i/N] half=... out=...` progress, then "wrote reports/learning/cb_threshold_stability_<date>.md". Check that the file exists, has the variant table, and has a plateau-check section. Delete the report if you want a clean run on the full window next.

- [ ] **Step 3: Run on full window**

```bash
python3 scripts/run_cb_threshold_stability.py
```
Expected: completes in 5-10 minutes; report shows the production choice with **PROD** tag and a plateau verdict.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_cb_threshold_stability.py reports/learning/cb_threshold_stability_*.md
git commit -m "research: CB threshold stability sweep (~80-cell grid)

Validates that the production 5%/8%/8%/12% choice sits on a plateau,
not a spike. Reports CAGR/MaxDD bands within ±1pp of each threshold.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Strategy A SMA-window stability sweep

**Files:**
- Create: `scripts/run_sma_stability.py`

Strategy A uses a 10-month SMA filter (Faber TAA). Sweep 8/9/10/11/12 months and confirm the chosen 10 isn't an isolated win.

This requires plumbing a SMA-window override through `lib.signals`. Look at `lib/signals.py` — Strategy A's risk-on/risk-off filter is currently hardcoded to ~10 months (about 210 trading days). The sweep needs to call the strategy with different windows.

- [ ] **Step 1: Inspect Strategy A's SMA usage in lib/signals.py**

```bash
grep -n "sma\|SMA\|monthly\|10.month\|210" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/lib/signals.py | head -20
```
Expected: locate where the 10-month (or ~210-trading-day) lookback is hardcoded. Note the exact constant or function call.

- [ ] **Step 2: Add an optional `sma_months` parameter to the Strategy A function**

Locate the function (likely `dual_momentum_taa` or similar). Add a keyword argument `sma_months: int = 10` and thread it through to the SMA computation. Default unchanged.

Then verify existing tests still pass:
```bash
python3 -m pytest tests/test_signals.py -v
```
Expected: all existing tests pass (default behavior unchanged).

- [ ] **Step 3: Add a regression test pinning the default**

In `tests/test_signals.py`, add a test that calls the function with `sma_months=10` explicitly and asserts the result equals the default-call result. This guarantees the parameter is wired correctly without changing behavior.

```python
def test_dual_momentum_taa_sma_months_default_matches_explicit():
    # ... build the same bars dict you use in existing tests ...
    default = dual_momentum_taa(bars, ...)
    explicit = dual_momentum_taa(bars, ..., sma_months=10)
    assert default == explicit
```
Run: `python3 -m pytest tests/test_signals.py -v` — passes.

- [ ] **Step 4: Plumb `sma_months` through `run_multi_strategy_backtest.run_backtest()`**

Add to argparse:
```python
parser.add_argument("--sma-months", type=int, default=10,
                    help="Strategy A trend-filter SMA window in months (default 10)")
```
Pass it into the Strategy A invocation inside `run_backtest()`.

Re-run the existing backtest test (Task 1, Step 4): `python3 -m pytest tests/ -v` — all pass.

- [ ] **Step 5: Create `scripts/run_sma_stability.py`**

```python
# scripts/run_sma_stability.py
"""SMA-window stability sweep for Strategy A.

Runs the full multi-strategy backtest 5 times with sma_months in {8,9,10,11,12}
and prints/writes the comparison. Production choice is 10.

Pass criterion: across 8-12 months, CAGR within ±1.5pp and MaxDD within ±2pp.

Usage: python scripts/run_sma_stability.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_multi_strategy_backtest as mod  # noqa: E402

WINDOWS = [8, 9, 10, 11, 12]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2013-05-24")
    parser.add_argument("--end", default="2026-05-08")
    args = parser.parse_args()

    rows = []
    for w in WINDOWS:
        print(f"[sma] testing sma_months={w}")
        ns = SimpleNamespace(
            start=args.start, end=args.end, capital=100_000.0,
            alloc_a=0.60, alloc_b=0.30, alloc_c=0.10,
            cash_buffer_pct=0.0,
            circuit_breaker=True,
            cb_half_dd=0.08, cb_out_dd=0.12,
            cb_recovery_dd=0.05, cb_out_recover_dd=0.08,
            sma_months=w,
            label=f"sma_{w}",
            write_report=False,
        )
        r = mod.run_backtest(ns)
        rows.append({"sma": w, "cagr": r["ann_return"], "mdd": r["max_drawdown_pct"],
                     "sharpe": r["sharpe"], "n_events": len(r["cb_events"])})

    cagrs = [r["cagr"] for r in rows]
    mdds = [r["mdd"] for r in rows]
    cagr_band = max(cagrs) - min(cagrs)
    mdd_band = max(mdds) - min(mdds)
    plateau = cagr_band <= 1.5 and mdd_band <= 2.0

    out = REPO_ROOT / "reports" / "learning" / (
        f"sma_window_stability_{datetime.utcnow():%Y-%m-%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Strategy A SMA-Window Stability — {datetime.utcnow():%Y-%m-%d}",
        "",
        f"Window: {args.start} → {args.end}",
        "",
        "| SMA months | CAGR % | MaxDD % | Sharpe | CB events | tag |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        tag = " **PROD**" if r["sma"] == 10 else ""
        lines.append(f"| {r['sma']} | {r['cagr']:+.2f} | {r['mdd']:.2f} | "
                     f"{r['sharpe']:.2f} | {r['n_events']} |{tag} |")
    lines += [
        "",
        "## Plateau check (8 ≤ months ≤ 12)",
        "",
        f"- CAGR band: {cagr_band:.2f}pp (gate: ≤ 1.5pp)",
        f"- MaxDD band: {mdd_band:.2f}pp (gate: ≤ 2.0pp)",
        f"- **Verdict:** {'PASS — broad plateau' if plateau else 'FAIL — SMA choice is on a peak'}",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[sma] wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run it**

```bash
python3 scripts/run_sma_stability.py
```
Expected: 5 backtest runs, then report at `reports/learning/sma_window_stability_<date>.md`. Read the verdict; if FAIL, surface to user before committing.

- [ ] **Step 7: Commit**

```bash
git add lib/signals.py tests/test_signals.py scripts/run_multi_strategy_backtest.py scripts/run_sma_stability.py reports/learning/sma_window_stability_*.md
git commit -m "research: Strategy A SMA-window stability sweep (8-12 months)

Plumbs sma_months through Strategy A and the backtest entry. Default
unchanged. Sweep confirms 10-month choice is on a plateau (or surfaces
that it isn't).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Walk-forward harness for CB thresholds

**Files:**
- Create: `scripts/run_walk_forward.py`
- Create: `tests/test_walk_forward.py`
- Create: `lib/walk_forward.py` (pure helpers — slicing windows, picking best by Sharpe, aggregating OOS metrics)

This is the most important script in the plan. It does true walk-forward: at time T, only use data up to T to pick CB thresholds, then evaluate on (T, T+1y]. Repeat for T = 2018, 2019, …, 2025. The OOS-aggregated metrics are the honest performance estimate.

- [ ] **Step 1: Write tests for the pure helpers (TDD)**

```python
# tests/test_walk_forward.py
"""Pure-function tests for lib.walk_forward — no network, no backtest calls."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.walk_forward import generate_windows, select_best, aggregate_oos  # noqa: E402


def test_generate_windows_5y_is_1y_oos_step_1y():
    """Standard config: 5-year IS, 1-year OOS, advance by 1 year."""
    windows = generate_windows(
        full_start="2010-01-01", full_end="2020-01-01",
        is_years=5, oos_years=1, step_years=1,
    )
    # First IS: 2010 → 2014 (exclusive end), OOS: 2015 → 2016
    # Last IS:  2014 → 2018,                OOS: 2019 → 2020
    assert windows[0] == ("2010-01-01", "2015-01-01", "2015-01-01", "2016-01-01")
    assert windows[-1] == ("2014-01-01", "2019-01-01", "2019-01-01", "2020-01-01")
    assert len(windows) == 5  # 2015,16,17,18,19 OOS years


def test_generate_windows_rejects_window_past_end():
    """If OOS would extend past full_end, omit that fold."""
    windows = generate_windows(
        full_start="2010-01-01", full_end="2016-06-30",
        is_years=5, oos_years=1, step_years=1,
    )
    # IS 2010→2015, OOS 2015→2016 fits. IS 2011→2016, OOS 2016→2017 does NOT fit (2017 > 2016-06-30).
    assert len(windows) == 1


def test_select_best_picks_highest_sharpe():
    """select_best returns the params dict with highest Sharpe from candidates."""
    candidates = [
        {"params": {"h": 0.08}, "metrics": {"sharpe": 0.9, "cagr": 10.0, "mdd": 12.0}},
        {"params": {"h": 0.07}, "metrics": {"sharpe": 1.2, "cagr": 11.0, "mdd": 13.0}},
        {"params": {"h": 0.09}, "metrics": {"sharpe": 1.1, "cagr": 12.0, "mdd": 14.0}},
    ]
    best = select_best(candidates, by="sharpe")
    assert best["params"] == {"h": 0.07}


def test_select_best_with_dd_constraint_rejects_winners_over_cap():
    """If a candidate breaches the DD cap, it cannot be selected even with best Sharpe."""
    candidates = [
        {"params": {"h": 0.08}, "metrics": {"sharpe": 1.5, "cagr": 11.0, "mdd": 18.0}},
        {"params": {"h": 0.07}, "metrics": {"sharpe": 1.1, "cagr": 10.0, "mdd": 13.0}},
    ]
    best = select_best(candidates, by="sharpe", max_mdd_pct=15.0)
    assert best["params"] == {"h": 0.07}, "should reject the high-Sharpe high-DD winner"


def test_aggregate_oos_chain_concatenates_returns():
    """OOS aggregator concatenates daily returns across folds and reports headline metrics."""
    # Two folds, each with 252 trading days of constant 0.0004 daily returns
    folds = [
        {"oos_daily_returns": [0.0004] * 252,
         "oos_metrics": {"sharpe": 1.0, "cagr": 10.5, "mdd": 5.0}},
        {"oos_daily_returns": [0.0003] * 252,
         "oos_metrics": {"sharpe": 0.9, "cagr": 7.8, "mdd": 4.0}},
    ]
    agg = aggregate_oos(folds)
    assert "chained_cagr" in agg
    assert "chained_mdd" in agg
    assert "chained_sharpe" in agg
    assert 7.0 < agg["chained_cagr"] < 12.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_walk_forward.py -v
```
Expected: `ModuleNotFoundError: No module named 'lib.walk_forward'`

- [ ] **Step 3: Create `lib/walk_forward.py` with the pure helpers**

```python
# lib/walk_forward.py
"""Pure helpers for walk-forward evaluation.

No network, no I/O, no backtest engine — just window arithmetic and
metric aggregation. The driver script in scripts/run_walk_forward.py
combines these with the backtest engine.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta


def _add_years(d: str, years: int) -> str:
    """Add an integer number of years to an ISO date string."""
    parsed = datetime.strptime(d, "%Y-%m-%d").date()
    try:
        return parsed.replace(year=parsed.year + years).isoformat()
    except ValueError:
        # Feb 29 → Feb 28 fallback
        return parsed.replace(year=parsed.year + years, day=28).isoformat()


def generate_windows(
    *, full_start: str, full_end: str,
    is_years: int, oos_years: int, step_years: int,
) -> list[tuple[str, str, str, str]]:
    """Generate (is_start, is_end, oos_start, oos_end) windows.

    is_end == oos_start (no gap). Folds whose oos_end > full_end are dropped.
    Returns ISO date strings.
    """
    out: list[tuple[str, str, str, str]] = []
    cur_is_start = full_start
    while True:
        is_end = _add_years(cur_is_start, is_years)
        oos_end = _add_years(is_end, oos_years)
        if oos_end > full_end:
            break
        out.append((cur_is_start, is_end, is_end, oos_end))
        cur_is_start = _add_years(cur_is_start, step_years)
    return out


def select_best(
    candidates: list[dict],
    *,
    by: str = "sharpe",
    max_mdd_pct: float | None = None,
) -> dict:
    """Pick the candidate with the highest `by` metric, subject to a DD cap.

    `candidates` items are {"params": {...}, "metrics": {sharpe, cagr, mdd, ...}}.
    Raises ValueError if no candidate satisfies the constraint.
    """
    eligible = candidates
    if max_mdd_pct is not None:
        eligible = [c for c in candidates if c["metrics"].get("mdd", math.inf) <= max_mdd_pct]
    if not eligible:
        raise ValueError(f"no candidate satisfies max_mdd_pct={max_mdd_pct}")
    return max(eligible, key=lambda c: c["metrics"].get(by, -math.inf))


def aggregate_oos(folds: list[dict]) -> dict:
    """Chain OOS daily returns across folds; report CAGR / MaxDD / Sharpe.

    Each fold dict must have 'oos_daily_returns' (list of float).
    """
    chained: list[float] = []
    for f in folds:
        chained.extend(f["oos_daily_returns"])
    if not chained:
        return {"chained_cagr": 0.0, "chained_mdd": 0.0, "chained_sharpe": 0.0,
                "n_days": 0}

    # Equity curve from chained returns
    equity = [1.0]
    for r in chained:
        equity.append(equity[-1] * (1.0 + r))

    n_days = len(chained)
    years = n_days / 252.0
    chained_cagr = ((equity[-1]) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else 0.0

    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100.0
        if dd > mdd:
            mdd = dd

    if len(chained) > 1:
        mean = sum(chained) / len(chained)
        var = sum((r - mean) ** 2 for r in chained) / (len(chained) - 1)
        std = math.sqrt(var)
        chained_sharpe = (mean / std * math.sqrt(252.0)) if std > 0 else 0.0
    else:
        chained_sharpe = 0.0

    return {
        "chained_cagr": chained_cagr,
        "chained_mdd": mdd,
        "chained_sharpe": chained_sharpe,
        "n_days": n_days,
    }
```

- [ ] **Step 4: Run the helper tests**

```bash
python3 -m pytest tests/test_walk_forward.py -v
```
Expected: 5 PASS.

- [ ] **Step 5: Create the walk-forward driver script**

```python
# scripts/run_walk_forward.py
"""Walk-forward CB threshold evaluation.

For each fold:
  1. On the IS window, sweep a small CB threshold grid and pick the best
     by Sharpe subject to MaxDD ≤ 15%.
  2. Run that chosen threshold on the OOS window.
  3. Record OOS metrics + the chosen params.

Then chain OOS daily returns across folds and report aggregate
CAGR / MaxDD / Sharpe — the honest forward-performance estimate.

Usage:
    python scripts/run_walk_forward.py [--full-start YYYY-MM-DD] [--full-end YYYY-MM-DD]
                                       [--is-years 5] [--oos-years 1] [--step-years 1]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.walk_forward import generate_windows, select_best, aggregate_oos  # noqa: E402
from scripts import run_multi_strategy_backtest as mod  # noqa: E402

# Smaller IS grid than Task 2 — walk-forward runs this 5-10 times per fold
# so we cap candidates to keep total runtime reasonable.
IS_GRID = [
    # (half_dd, out_dd, half_to_full, out_to_half)
    (0.06, 0.10, 0.04, 0.07),
    (0.07, 0.11, 0.05, 0.08),
    (0.08, 0.12, 0.05, 0.08),  # production choice
    (0.09, 0.13, 0.06, 0.09),
    (0.10, 0.14, 0.07, 0.10),
]


def make_args(start, end, h, o, htf, oth):
    return SimpleNamespace(
        start=start, end=end, capital=100_000.0,
        alloc_a=0.60, alloc_b=0.30, alloc_c=0.10,
        cash_buffer_pct=0.0,
        circuit_breaker=True,
        cb_half_dd=h, cb_out_dd=o,
        cb_recovery_dd=htf, cb_out_recover_dd=oth,
        sma_months=10,
        label="wf",
        write_report=False,
    )


def daily_returns_from_curve(curve: list[tuple[str, float]]) -> list[float]:
    if len(curve) < 2:
        return []
    return [(curve[i][1] / curve[i - 1][1]) - 1.0 for i in range(1, len(curve))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-start", default="2013-05-24")
    parser.add_argument("--full-end", default="2026-05-08")
    parser.add_argument("--is-years", type=int, default=5)
    parser.add_argument("--oos-years", type=int, default=1)
    parser.add_argument("--step-years", type=int, default=1)
    args = parser.parse_args()

    folds = generate_windows(
        full_start=args.full_start, full_end=args.full_end,
        is_years=args.is_years, oos_years=args.oos_years, step_years=args.step_years,
    )
    print(f"[wf] {len(folds)} folds | IS {args.is_years}y / OOS {args.oos_years}y / "
          f"step {args.step_years}y")

    fold_records = []
    for i, (is_s, is_e, oos_s, oos_e) in enumerate(folds, 1):
        print(f"\n[wf fold {i}/{len(folds)}] IS {is_s}→{is_e} | OOS {oos_s}→{oos_e}")

        # IS sweep
        is_results = []
        for (h, o, htf, oth) in IS_GRID:
            r = mod.run_backtest(make_args(is_s, is_e, h, o, htf, oth))
            is_results.append({
                "params": {"half_dd": h, "out_dd": o, "h_to_f": htf, "o_to_h": oth},
                "metrics": {"sharpe": r["sharpe"], "cagr": r["ann_return"],
                            "mdd": r["max_drawdown_pct"]},
            })

        chosen = select_best(is_results, by="sharpe", max_mdd_pct=15.0)
        p = chosen["params"]
        print(f"  IS chose: half={p['half_dd']:.2f} out={p['out_dd']:.2f} "
              f"h→f={p['h_to_f']:.2f} o→h={p['o_to_h']:.2f} "
              f"(IS Sharpe={chosen['metrics']['sharpe']:.2f})")

        # OOS run with chosen params
        oos = mod.run_backtest(make_args(oos_s, oos_e,
                                         p["half_dd"], p["out_dd"],
                                         p["h_to_f"], p["o_to_h"]))
        oos_returns = daily_returns_from_curve(oos["equity_curve"])
        print(f"  OOS: CAGR={oos['ann_return']:+.2f}% "
              f"MDD={oos['max_drawdown_pct']:.2f}% Sharpe={oos['sharpe']:.2f}")

        fold_records.append({
            "is_start": is_s, "is_end": is_e, "oos_start": oos_s, "oos_end": oos_e,
            "chosen_params": p,
            "is_metrics": chosen["metrics"],
            "oos_metrics": {"sharpe": oos["sharpe"], "cagr": oos["ann_return"],
                            "mdd": oos["max_drawdown_pct"]},
            "oos_daily_returns": oos_returns,
        })

    agg = aggregate_oos(fold_records)
    print(f"\n[wf aggregate OOS] {agg['n_days']} days | "
          f"CAGR={agg['chained_cagr']:+.2f}% | "
          f"MDD={agg['chained_mdd']:.2f}% | "
          f"Sharpe={agg['chained_sharpe']:.2f}")

    out = REPO_ROOT / "reports" / "learning" / (
        f"walk_forward_cb_{datetime.utcnow():%Y-%m-%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Walk-Forward CB Threshold Evaluation — {datetime.utcnow():%Y-%m-%d}",
        "",
        f"Window: {args.full_start} → {args.full_end}",
        f"Folds: {len(folds)} | IS {args.is_years}y | OOS {args.oos_years}y | "
        f"Step {args.step_years}y",
        f"IS grid: {len(IS_GRID)} candidate threshold sets per fold",
        f"Selection rule: max IS Sharpe subject to IS MaxDD ≤ 15%",
        "",
        "## Per-fold results",
        "",
        "| Fold | IS window | OOS window | Chosen (h/o/h→f/o→h) | IS Sharpe | OOS CAGR % | OOS MDD % | OOS Sharpe |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for i, rec in enumerate(fold_records, 1):
        p = rec["chosen_params"]
        lines.append(
            f"| {i} | {rec['is_start']}→{rec['is_end']} | "
            f"{rec['oos_start']}→{rec['oos_end']} | "
            f"{p['half_dd']:.2f}/{p['out_dd']:.2f}/{p['h_to_f']:.2f}/{p['o_to_h']:.2f} | "
            f"{rec['is_metrics']['sharpe']:.2f} | "
            f"{rec['oos_metrics']['cagr']:+.2f} | "
            f"{rec['oos_metrics']['mdd']:.2f} | "
            f"{rec['oos_metrics']['sharpe']:.2f} |"
        )

    # Headline OOS-chained results
    lines += [
        "",
        "## Aggregated OOS performance (chained daily returns)",
        "",
        f"- Total OOS trading days: {agg['n_days']}",
        f"- **OOS CAGR: {agg['chained_cagr']:+.2f}%**",
        f"- **OOS MaxDD: {agg['chained_mdd']:.2f}%**",
        f"- **OOS Sharpe: {agg['chained_sharpe']:.2f}**",
        "",
        "## Comparison vs in-sample full-window run",
        "",
        "Full-window IS (production thresholds, 2013-05-24 → 2026-05-08):",
        "- CAGR: +11.15% | MaxDD: 12.68% | Sharpe: 1.14 (per `pivot_validation_2026-05-10.md`)",
        "",
        f"OOS-chained: CAGR {agg['chained_cagr']:+.2f}% | MaxDD {agg['chained_mdd']:.2f}% | "
        f"Sharpe {agg['chained_sharpe']:.2f}",
        "",
        "**Interpretation guide:**",
        "- If OOS CAGR > IS - 2pp AND OOS MDD < IS + 3pp → no overfitting evidence.",
        "- If OOS CAGR < IS - 4pp OR OOS MDD > IS + 5pp → overfitting concern; review.",
        "- If chosen params differ substantially across folds → CB choice is regime-dependent;",
        "  document and consider regime-conditional thresholds (deferred to future work).",
        "",
        "## Caveats",
        "- 5-year IS window means first usable OOS year is "
        f"{folds[0][2] if folds else 'N/A'}.",
        "- yfinance survivor bias on Strategy B's universe affects all folds equally.",
        "- IS grid is intentionally small (5 candidates) to bound runtime; a larger grid",
        "  could find better fold-by-fold IS Sharpe but would amplify in-sample overfit risk.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[wf] wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run the walk-forward**

```bash
python3 scripts/run_walk_forward.py
```
Expected: ~9 folds × 5 IS runs + 1 OOS run = 54 backtests; ~5-10 min runtime. Final aggregate-OOS line printed; report at `reports/learning/walk_forward_cb_<date>.md`.

- [ ] **Step 7: Read the report and write a 5-line summary to add to plan.md**

Look at the report's interpretation-guide section and the actual OOS-chained numbers. Surface to the user (don't auto-update plan.md):
- OOS CAGR vs IS CAGR
- OOS MDD vs IS MDD
- Whether the chosen params were stable across folds (a single threshold set won most folds → robust; different thresholds every fold → regime-dependent)

- [ ] **Step 8: Commit**

```bash
git add lib/walk_forward.py tests/test_walk_forward.py scripts/run_walk_forward.py reports/learning/walk_forward_cb_*.md
git commit -m "research: walk-forward CB threshold evaluation harness

5y IS / 1y OOS / 1y step folds. Picks best CB thresholds by IS Sharpe
subject to MaxDD ≤ 15%, evaluates on next year. Chains OOS daily
returns to produce honest forward-performance estimate.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Update plan.md "Still open" with results

**Files:**
- Modify: `plan.md` (the "Still open" section around line 191)

After running Tasks 2-4, the "Still open" line about parameter stability is closed. Update it.

- [ ] **Step 1: Read the current "Still open" section**

```bash
grep -n "Still open" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/plan.md
```
Expected: line ~191. Read 20 lines from there.

- [ ] **Step 2: Add a new dated subsection above "Still open"**

Use Edit to insert a new section "### Walk-forward + parameter stability — landed YYYY-MM-DD" with:
- One-paragraph summary of what landed (the 3 sweep scripts + 1 walk-forward script).
- The headline OOS-chained CAGR / MaxDD / Sharpe numbers from the walk-forward report.
- The plateau verdict from the CB stability sweep.
- Link to the three reports in `reports/learning/`.

- [ ] **Step 3: Commit**

```bash
git add plan.md
git commit -m "docs(plan): record walk-forward + parameter stability results"
```

---

## Self-Review Checklist

Run through these before declaring the plan done:

1. **Spec coverage:** All four sub-items addressed? ✓ Walk-forward (Task 4), CB threshold stability (Task 2), SMA stability (Task 3), refactor enabling all of it (Task 1), plan.md update (Task 5).
2. **Placeholders:** None. Every step has runnable code or commands.
3. **Type consistency:** `run_backtest()` returns dict with keys `ann_return`, `max_drawdown_pct`, `sharpe`, `final_equity`, `cb_events`, `n_trades`, `equity_curve`, `overall`, `hit_low`, `hit_high`, `dd_ok`, `sharpe_ok`. Used consistently across Tasks 2, 3, 4.
4. **No production-config edits:** Confirmed — only new scripts/tests/lib helpers and a plan.md doc update.

## Stopping Conditions

If any of these occur, stop and surface to the user before continuing:

- The CB threshold stability sweep verdict is **FAIL** (CAGR band > 1.5pp or MDD band > 2pp around production choice). The production thresholds may need to be re-chosen.
- The SMA stability sweep verdict is **FAIL**.
- The walk-forward OOS CAGR is more than **4pp below** the IS CAGR, or OOS MDD is more than **5pp above** IS MDD. This is overfitting evidence and should pause any thoughts of going live.
- Chosen IS parameters differ substantially across folds (e.g., different best-half_dd in > 50% of folds). The CB design is regime-dependent and the system needs a regime-conditional breaker, not a single fixed set of thresholds.
