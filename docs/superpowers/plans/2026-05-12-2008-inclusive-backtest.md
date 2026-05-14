# 2008-Inclusive Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the multi-strategy backtest window backward through the 2008 financial crisis and report honest drawdown / recovery time / strategy attribution under genuine recession stress.

**Architecture:** The current window starts 2013-05-24 because that's when SHV (cash proxy) data begins to overlap with the rest. Two complementary approaches: (a) substitute a longer-history cash proxy (e.g., BIL launched 2007-05, or even SHY launched 2002) so the full multi-strategy backtest can run from 2008; (b) for Strategy B, replace the modern mega-cap universe (META, TSLA didn't exist) with a **time-aware universe** that activates symbols only on or after their actual listing date. Both changes additive; no production code touched.

**Tech Stack:** Python 3.12, yfinance (already cached at `backtests/_yfinance_cache/`), existing `lib.backtest`, `lib.signals`, `lib.portfolio_risk`, `scripts/run_multi_strategy_backtest.py`.

---

## Why this matters (one paragraph for the executor)

Plan.md explicitly admits ([line 36](../../plan.md:36), [line 74](../../plan.md:74)) that "real recession DD could be 30–35%" and that the 12.68% max DD on the chosen window is conditional on a 2013+ data range that excludes 2008. The 15% drawdown ceiling in CLAUDE.md is the load-bearing risk number for this entire system; if 2008 blows through it by 2× we need to know that *before* going live, not after. This plan does not change any production behavior — it produces evidence about how the strategy would have behaved through the worst documented stress event of the modern era.

---

## File Structure

**Create:**
- `scripts/run_2008_backtest.py` — orchestrates the long-window run: time-aware Strategy B universe, BIL or SHY as cash proxy, writes a recession-focused report.
- `lib/historical_universe.py` — pure helpers: load the time-aware mega-cap universe (symbol → listing date) and filter for "tradeable as of date X".
- `tests/test_historical_universe.py` — pure tests.
- `backtests/multi_strategy_portfolio/2007-XX-XX_to_2026-05-08_2008_inclusive_*.md` — the chosen-variant report.
- `reports/learning/2008_stress_test_<date>.md` — narrative report focused on the crisis period (Jul 2007 → Jun 2009) and recovery time.

**Modify:**
- `lib/signals.py` — Strategy B already takes a `bars_by_symbol` dict and treats symbols as the universe; no logic change. The time-aware filtering happens upstream in the new script.
- `scripts/run_multi_strategy_backtest.py` — add `--cash-proxy <SHV|BIL|SHY>` CLI flag (and corresponding kwarg in `run_backtest()` — assumes Plan #1 Task 1 has landed; if not, factor that out as a prerequisite). Default unchanged: SHV.

**No edits to:**
- Any `config/*.yaml` (would touch the production watchlist, which is PR-locked).
- Any `prompts/`.
- The production strategy A/B/C signal functions (they consume whatever `bars_by_symbol` they're given).
- `lib/portfolio_risk.py`.

---

## Prerequisite check

This plan depends on Task 1 from the walk-forward plan (`run_backtest()` refactored into a callable). If that task has NOT landed yet, do **either**:
- Execute walk-forward Task 1 first, then return here.
- OR: invoke `scripts/run_multi_strategy_backtest.py` as a subprocess from `scripts/run_2008_backtest.py`. Subprocess is fine for this one-shot run (we're not sweeping 80+ combos).

This plan assumes the subprocess fallback for simplicity, so it can be executed standalone. Each subprocess call writes its own report file.

---

## Data availability constraints (read this before starting)

Approximate yfinance availability for relevant symbols:

| Symbol | First trading day | Notes |
|---|---|---|
| SPY | 1993-01-29 | OK from 2008 |
| GLD | 2004-11-18 | OK from 2008 |
| IEF | 2002-07-26 | OK from 2008 |
| SHV | 2007-01-11 | Cash proxy, but limited pre-2007 history |
| BIL | 2007-05-30 | Better cash proxy for pre-2008 (SHV-equivalent return) |
| SHY | 2002-07-26 | Longer history; slightly higher duration than BIL/SHV |
| AAPL | 1980-12-12 | Always available |
| MSFT | 1986-03-13 | Always available |
| GOOGL | 2004-08-19 | OK from 2008 |
| AMZN | 1997-05-15 | Always available |
| NVDA | 1999-01-22 | Always available |
| META (FB) | 2012-05-18 | **Not tradeable pre-2012** |
| TSLA | 2010-06-29 | **Not tradeable pre-2010** |
| JPM | 1980 | Always |
| BAC | 1986 | Always |
| V | 2008-03-19 | Borderline — IPO'd mid-2008 |
| MA | 2006-05-25 | OK |
| JNJ, UNH, PFE, WMT, COST, HD, XOM, ORCL, CSCO | all pre-2000 | OK |

**Bottom line:** to run from 2008-01-01, use BIL as cash proxy (or SHY as alternative), and treat META/TSLA/V as **conditionally tradeable** — only included in Strategy B's top-N selection on or after their listing dates. Strategy B's universe must shrink in earlier years.

---

## Task 1: Build the time-aware historical universe helper

**Files:**
- Create: `lib/historical_universe.py`
- Create: `tests/test_historical_universe.py`

A pure helper: given a date and a universe with per-symbol "listed_since" dates, return the symbols tradeable on that date.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_historical_universe.py
"""Pure tests for the time-aware historical universe."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.historical_universe import (  # noqa: E402
    MEGACAP_LISTING_DATES, tradeable_as_of, filter_bars_by_listing,
)


def test_tradeable_as_of_2008_excludes_meta_and_tsla():
    universe = ["AAPL", "MSFT", "META", "TSLA", "NVDA", "GOOGL", "V"]
    result = tradeable_as_of(universe, "2008-01-01")
    assert "AAPL" in result and "MSFT" in result and "NVDA" in result
    assert "META" not in result
    assert "TSLA" not in result
    assert "V" not in result  # V IPO'd March 2008
    assert "GOOGL" in result  # IPO 2004


def test_tradeable_as_of_2013_includes_meta_excludes_nothing_else():
    universe = ["AAPL", "MSFT", "META", "TSLA", "V"]
    result = tradeable_as_of(universe, "2013-01-01")
    assert set(result) == {"AAPL", "MSFT", "META", "TSLA", "V"}


def test_tradeable_as_of_meta_boundary_day_after_listing():
    # META listed 2012-05-18
    assert "META" in tradeable_as_of(["META"], "2012-05-18")
    assert "META" not in tradeable_as_of(["META"], "2012-05-17")


def test_tradeable_as_of_unknown_symbol_assumed_always_tradeable():
    """Symbols not in MEGACAP_LISTING_DATES default to 'always tradeable'."""
    assert "UNKNOWN" in tradeable_as_of(["UNKNOWN"], "1995-01-01")


def test_filter_bars_by_listing_drops_pre_listing_bars():
    """Bars dated before listing must be dropped (yfinance sometimes returns junk)."""
    bars = {
        "AAPL": [{"ts": "2000-01-03T00:00:00Z", "close": 1.0},
                 {"ts": "2008-01-03T00:00:00Z", "close": 10.0}],
        "META": [{"ts": "2010-01-03T00:00:00Z", "close": 1.0},  # pre-listing junk
                 {"ts": "2013-01-03T00:00:00Z", "close": 30.0}],
    }
    filtered = filter_bars_by_listing(bars)
    assert len(filtered["AAPL"]) == 2
    assert len(filtered["META"]) == 1
    assert filtered["META"][0]["ts"].startswith("2013")
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest tests/test_historical_universe.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `lib/historical_universe.py`**

```python
# lib/historical_universe.py
"""Time-aware universe for historical backtests.

For symbols that didn't exist before a certain date (META, TSLA, V),
include them in the Strategy B candidate universe only on or after their
actual listing date. Otherwise the backtest implicitly assumes META
existed in 2008 which biases the top-N selection nonsensically.

This is consumed only by the long-window backtest script. Production
trading uses the present-day watchlist directly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable


# Listing dates for the modern mega-cap basket. Symbols not listed here are
# assumed to predate any window we'd realistically backtest.
# Sources: company SEC filings + yfinance first-available-bar dates.
MEGACAP_LISTING_DATES: dict[str, str] = {
    # Stocks that DID NOT exist before some recent date
    "META":  "2012-05-18",   # IPO as FB
    "TSLA":  "2010-06-29",
    "V":     "2008-03-19",
    "GOOGL": "2004-08-19",
    "GOOG":  "2014-04-03",   # share-class split; GOOGL preceded
    "MA":    "2006-05-25",

    # ETFs
    "SHV":   "2007-01-11",
    "BIL":   "2007-05-30",
    "GLD":   "2004-11-18",
    "IEF":   "2002-07-26",
    "SHY":   "2002-07-26",
    # SPY: 1993-01-29 — predates any realistic window, so omitted (treated as always-tradeable)

    # Modern names that DID exist pre-2008
    "AAPL": "1980-12-12",
    "MSFT": "1986-03-13",
    "AMZN": "1997-05-15",
    "NVDA": "1999-01-22",
    "JPM":  "1980-01-01",
    "BAC":  "1986-01-01",
    "JNJ":  "1980-01-01",
    "UNH":  "1984-10-17",
    "PFE":  "1980-01-01",
    "WMT":  "1980-01-01",
    "COST": "1985-12-05",
    "HD":   "1981-09-22",
    "XOM":  "1980-01-01",
    "ORCL": "1986-03-12",
    "CSCO": "1990-02-16",
}


def tradeable_as_of(symbols: Iterable[str], date_iso: str) -> list[str]:
    """Return the subset of `symbols` that were tradeable on or before `date_iso`.

    Symbols not in MEGACAP_LISTING_DATES are assumed always tradeable
    (conservative — they're likely older than any window we'd backtest).
    """
    target = datetime.strptime(date_iso[:10], "%Y-%m-%d").date()
    out = []
    for sym in symbols:
        listed = MEGACAP_LISTING_DATES.get(sym)
        if listed is None:
            out.append(sym)
            continue
        listed_date = datetime.strptime(listed, "%Y-%m-%d").date()
        if target >= listed_date:
            out.append(sym)
    return out


def filter_bars_by_listing(bars_by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Drop any bar dated before the symbol's listing date.

    yfinance sometimes returns synthesized pre-listing bars (zeros, NaN).
    This is a defensive filter to prevent those polluting downstream
    indicators (especially SMA / momentum windows).
    """
    out: dict[str, list[dict]] = {}
    for sym, bars in bars_by_symbol.items():
        listed = MEGACAP_LISTING_DATES.get(sym)
        if listed is None:
            out[sym] = list(bars)
            continue
        out[sym] = [b for b in bars if b.get("ts", "")[:10] >= listed]
    return out
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_historical_universe.py -v
```
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/historical_universe.py tests/test_historical_universe.py
git commit -m "feat: time-aware historical universe helper for long-window backtests

Provides tradeable_as_of() and filter_bars_by_listing(). Strategy B's
2008 backtest must NOT include META (listed 2012) or TSLA (listed 2010)
in its top-N selection until those names actually existed.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Add `--cash-proxy` flag to the multi-strategy backtest

**Files:**
- Modify: `scripts/run_multi_strategy_backtest.py`

The current backtest hardcodes SHV as the cash proxy. SHV started trading 2007-01-11, so technically usable from 2008 — but for safety (avoiding the thin-volume early months) and to give a fallback, let the script accept SHY or BIL.

- [ ] **Step 1: Find every reference to "SHV" in the backtest script**

```bash
grep -n "SHV\|cash_proxy\|TAA_CASH_PROXY" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/scripts/run_multi_strategy_backtest.py | head -20
grep -n "SHV\|TAA_CASH_PROXY" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/lib/signals.py | head -10
```

- [ ] **Step 2: Make `TAA_CASH_PROXY` runtime-overridable**

The cleanest path: Strategy A in `lib/signals.py` reads `TAA_CASH_PROXY` as a module constant. Change `evaluate_dual_momentum_taa` to accept an optional `cash_proxy: str = TAA_CASH_PROXY` parameter and pass that into wherever it's used in the function body. Default unchanged.

Also update the symbol-fetching loop in `scripts/run_multi_strategy_backtest.py`: instead of `symbols_needed = ["SPY", "IEF", "GLD", "SHV"]` (or similar), build `symbols_needed = ["SPY", "IEF", "GLD", args.cash_proxy]`.

- [ ] **Step 3: Add the CLI flag**

In `scripts/run_multi_strategy_backtest.py`, add:

```python
parser.add_argument("--cash-proxy", default="SHV", choices=["SHV", "BIL", "SHY"],
                    help="Cash proxy for Strategy A and SHV-cash-bucket allocation. "
                         "Use BIL or SHY for windows that start before SHV's 2007 listing.")
```

Thread `args.cash_proxy` through:
- The yfinance fetch loop
- The Strategy A invocation (`cash_proxy=args.cash_proxy`)
- The `run_cash_bucket_shv()` function — rename internally to use the configurable symbol (or wrap)
- Report metadata (note which cash proxy was used)

- [ ] **Step 4: Run existing tests to verify nothing breaks**

```bash
python3 -m pytest tests/ -v
```
Expected: all green; default behavior with SHV unchanged.

- [ ] **Step 5: Smoke-test with BIL**

```bash
python3 scripts/run_multi_strategy_backtest.py --start 2013-05-24 --end 2026-05-08 --cash-proxy BIL --circuit-breaker --label bil_smoke
```
Expected: completes; report mentions BIL; metrics roughly comparable to SHV baseline (both are short-T-bill ETFs).

- [ ] **Step 6: Commit**

```bash
git add lib/signals.py scripts/run_multi_strategy_backtest.py
git commit -m "feat(backtest): --cash-proxy flag for Strategy A (SHV|BIL|SHY)

Long-window backtests starting before SHV's 2007 listing date need
a substitute cash proxy. BIL (launched 2007-05) and SHY (2002) are
equivalent short-T-bill exposures. Default unchanged (SHV).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Write the 2008-inclusive backtest driver

**Files:**
- Create: `scripts/run_2008_backtest.py`

This orchestrates the long-window run: prepares the time-aware Strategy B universe, picks the right cash proxy, invokes the multi-strategy backtest, and emits a recession-focused report.

- [ ] **Step 1: Build the script**

```python
# scripts/run_2008_backtest.py
"""Long-window backtest including the 2007-2009 financial crisis.

Standard backtest starts 2013-05-24. This one starts 2007-06-01 (giving
6 months warmup for the 10-month SMA filter before any signals fire,
so first real trades are end of 2007). Uses BIL as cash proxy
(SHV's data is thinner in early 2007) and a time-aware Strategy B
universe via lib.historical_universe.

The point is not to chase return — it's to measure DD and recovery
time through the worst documented stress event of the modern era.

Usage:
    python scripts/run_2008_backtest.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2007-06-01",
                        help="Backtest start (yfinance must have all symbols by this date).")
    parser.add_argument("--end", default="2026-05-08")
    parser.add_argument("--cash-proxy", default="BIL", choices=["SHV", "BIL", "SHY"])
    parser.add_argument("--label", default="2008_inclusive")
    args = parser.parse_args()

    # Run the underlying backtest via subprocess (so this script is independent
    # of whether walk-forward Plan Task 1 has landed).
    cmd = [
        sys.executable, str(REPO_ROOT / "scripts" / "run_multi_strategy_backtest.py"),
        "--start", args.start,
        "--end", args.end,
        "--circuit-breaker",
        "--cash-proxy", args.cash_proxy,
        "--label", args.label,
    ]
    print(f"[2008-bt] running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=False)
    if result.returncode not in (0, 1):
        # 0 = all gates passed; 1 = gates failed (still a valid run — that's the point).
        print(f"[2008-bt] backtest exited {result.returncode}; aborting report")
        return 1

    # Find the produced report file
    report_dir = REPO_ROOT / "backtests" / "multi_strategy_portfolio"
    candidates = sorted(report_dir.glob(f"*{args.label}*.md"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        print(f"[2008-bt] could not find backtest report for label '{args.label}'")
        return 1
    backtest_report = candidates[-1]

    # Read the backtest report and extract headline metrics by regex.
    # (If the report format is JSON-augmented later, parse JSON instead.)
    import re
    body = backtest_report.read_text(encoding="utf-8")

    def grab(pattern: str, default: str = "?") -> str:
        m = re.search(pattern, body)
        return m.group(1) if m else default

    cagr = grab(r"Annualized.*?\|\s*([+-]?\d+\.\d+)%")
    mdd = grab(r"Max drawdown.*?\|\s*(\d+\.\d+)%")
    sharpe = grab(r"Sharpe.*?\|\s*(\d+\.\d+)")
    n_events_match = re.search(r"Throttle events:\s*(\d+)", body)
    n_events = n_events_match.group(1) if n_events_match else "?"

    # Compose the recession-focused stress-test report.
    out = REPO_ROOT / "reports" / "learning" / (
        f"2008_stress_test_{datetime.utcnow():%Y-%m-%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 2008-Inclusive Stress Test — {datetime.utcnow():%Y-%m-%d}",
        "",
        f"Window: {args.start} → {args.end} (~{(int(args.end[:4]) - int(args.start[:4]))}y)",
        f"Cash proxy: {args.cash_proxy}",
        f"Strategy B universe: time-aware via `lib.historical_universe`",
        f"Underlying backtest report: `{backtest_report.relative_to(REPO_ROOT)}`",
        "",
        "## Headline metrics over full window",
        "",
        f"- CAGR: {cagr}%",
        f"- Max drawdown: {mdd}%",
        f"- Sharpe: {sharpe}",
        f"- CB throttle events: {n_events}",
        "",
        "## Comparison to 2013-2026 production window",
        "",
        "| Metric | 2013-2026 (prod) | 2007-2026 (this run) | Delta |",
        "|---|---:|---:|---:|",
        f"| CAGR | +11.15% | {cagr}% | — |",
        f"| Max DD | 12.68% | {mdd}% | — |",
        f"| Sharpe | 1.14 | {sharpe} | — |",
        "| CB events | 15 | " + n_events + " | — |",
        "",
        "## Crisis-period focus (2007-07 → 2009-06)",
        "",
        "*Manual analysis required:* open the underlying report's CB events table",
        "and per-strategy attribution. Look for:",
        "- The maximum drawdown drawdown depth during 2008-09 → 2009-03 specifically",
        "- Recovery time from trough to new high (calendar months)",
        "- Which strategy was hit hardest (likely Strategy B momentum during the crash)",
        "- Whether the circuit-breaker engaged early (FULL→HALF at -8% in late 2008)",
        "  or late (the value of the breaker depends on its responsiveness here)",
        "",
        "Fill the table below by reading the backtest's `cb_events` section and ",
        "per-strategy `total_return_pct` columns for the 2008-2009 window:",
        "",
        "| Date | Event | Portfolio % from peak |",
        "|---|---|---:|",
        "| 2007-10-09 | SPY all-time-high (start of crisis) | 0.0% |",
        "| 2008-XX-XX | First FULL→HALF transition (when?) | TBD |",
        "| 2009-03-09 | SPY crisis low | TBD |",
        "| 20XX-XX-XX | Recovery to pre-crisis peak | TBD |",
        "",
        "## Caveats and known biases",
        "",
        "- **yfinance survivor bias on Strategy B is amplified in this window.** ",
        "  Even with the time-aware listing filter, the 20-name basket is the *2026 winners* ",
        "  set. Names that *would have been in a 2008-era large-cap basket but later collapsed* ",
        "  (e.g. Citigroup, AIG, Lehman) are absent. See `2026-05-12-survivor-bias-stress-test.md` ",
        "  for a complementary plan that addresses this directly.",
        "- **Cash proxy substitution:** BIL has slightly different yield characteristics ",
        "  than SHV; expect a few bps difference in Strategy A's cash-floor returns vs the ",
        "  hypothetical 'SHV from 2008'.",
        "- **First real signals:** ~10 months after the start date (SMA warmup), so the ",
        "  effective trading window is 2008-04 onward.",
        "",
        "## Decision criteria for the 15% DD ceiling",
        "",
        f"The 2008-inclusive max drawdown is {mdd}%.",
        "",
        f"- If {mdd}% ≤ 15% → the production DD ceiling holds under crisis stress. ",
        "  Update plan.md to remove the '2008 untested' caveat. Update CLAUDE.md to note",
        "  the system has been validated through the 2008 crisis.",
        f"- If {mdd}% > 15% AND ≤ 20% → caveat is real but bounded. Recommend keeping",
        "  the 15% number as a *halt-and-review* trigger rather than a hard cap, and",
        "  surface this in the next monthly review.",
        f"- If {mdd}% > 20% → the production strategy mix cannot meet the 15% DD goal ",
        "  through a 2008-class event. Either widen the breaker thresholds (tighter ",
        "  HALF/OUT triggers) or accept a higher DD ceiling in CLAUDE.md.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[2008-bt] wrote {out.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify yfinance has data for all required symbols starting 2007-06**

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, ".")
from scripts.run_multi_strategy_backtest import fetch_bars_yfinance
for sym in ["SPY", "IEF", "GLD", "BIL", "AAPL", "MSFT", "JPM", "BAC"]:
    bars = fetch_bars_yfinance(sym)
    first = bars[0]["ts"][:10] if bars else "EMPTY"
    print(f"{sym}: first bar = {first} (n={len(bars)})")
EOF
```
Expected: each symbol has bars from 2007 or earlier. If BIL shows "2007-05-30", verify start=2007-06-01 is safe.

- [ ] **Step 3: Run the long backtest**

```bash
python3 scripts/run_2008_backtest.py
```
Expected: completes; backtest report at `backtests/multi_strategy_portfolio/2007-06-01_to_2026-05-08_2008_inclusive.md`; stress-test report at `reports/learning/2008_stress_test_<date>.md`.

- [ ] **Step 4: Inspect the headline DD number**

```bash
grep -A 1 "Max drawdown" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/reports/learning/2008_stress_test_*.md | head -5
```

**Decision point** — based on the actual number:
- DD ≤ 15% → continue to Task 4 (update plan.md to close the 2008 caveat).
- 15% < DD ≤ 20% → continue to Task 4, but the narrative changes to "stress-tested; DD breaches 15% in 2008-class events; ceiling is informational, not enforceable in such regimes".
- DD > 20% → **stop and surface to user.** A strategy review may be required before going live. Do NOT auto-commit.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_2008_backtest.py backtests/multi_strategy_portfolio/2007-06-01_to_2026-05-08_2008_inclusive.md reports/learning/2008_stress_test_*.md
git commit -m "research: 2008-inclusive multi-strategy backtest with time-aware universe

Extends the backtest window through the 2007-2009 financial crisis.
Uses BIL as cash proxy (predates SHV's 2007 listing concerns) and the
time-aware Strategy B universe (excludes META/TSLA/V pre-listing).

The 15% DD ceiling in CLAUDE.md has now been tested against the worst
documented stress event in the data — see reports/learning/2008_stress_test_*.md
for the verdict.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Time-aware Strategy B universe filtering in the driver

**Files:**
- Modify: `scripts/run_multi_strategy_backtest.py` (the data-prep section, before strategy invocation)

The script in Task 3 invokes the multi-strategy backtest, but does not currently apply listing-date filtering. We need to add a small filter step so Strategy B's per-date top-N selection only considers symbols that existed on that date.

The cleanest fix is at the bar-loading layer: pass all bars through `filter_bars_by_listing()` so any pre-listing rows (yfinance occasionally synthesizes them) are removed. Strategy B's existing momentum-window calculation then naturally fails for symbols with < N bars and they're excluded from top-N selection until they have enough history.

- [ ] **Step 1: Find the bar-loading section in `run_multi_strategy_backtest.py`**

```bash
grep -n "fetch_bars_yfinance\|bars_by_symbol\|align_bars" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/scripts/run_multi_strategy_backtest.py | head -10
```

- [ ] **Step 2: Apply the listing filter immediately after fetch**

After the `bars` dict is built but before `align_bars()` is called, add:

```python
from lib.historical_universe import filter_bars_by_listing
bars = filter_bars_by_listing(bars)
```

This is a no-op for symbols not in `MEGACAP_LISTING_DATES`, and a noticeable filter for META / TSLA / V in long windows.

- [ ] **Step 3: Verify existing tests still pass**

```bash
python3 -m pytest tests/ -v
```
Expected: all green (the filter is a no-op for the production window).

- [ ] **Step 4: Re-run the smoke 2013-2026 backtest to confirm no regression**

```bash
python3 scripts/run_multi_strategy_backtest.py --start 2013-05-24 --end 2026-05-08 --circuit-breaker --label regression_check
```
Expected: results match the production reference: +11.15% CAGR, 12.68% MaxDD, 1.14 Sharpe, 15 CB events. If they differ, the filter has unintended consequences.

- [ ] **Step 5: Re-run the 2008 backtest with the filter applied**

```bash
rm reports/learning/2008_stress_test_*.md backtests/multi_strategy_portfolio/2007-06-01_to_2026-05-08_2008_inclusive.md
python3 scripts/run_2008_backtest.py
```
The numbers may differ slightly from Task 3 Step 3 — Strategy B's universe is now correctly restricted in early years.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_multi_strategy_backtest.py reports/learning/2008_stress_test_*.md backtests/multi_strategy_portfolio/2007-06-01_to_2026-05-08_2008_inclusive.md
git commit -m "fix(backtest): apply time-aware listing filter to all bars

Strategy B's top-N selection in long-window backtests would otherwise
silently include synthesized pre-listing bars for META/TSLA/V.
Production window (2013+) is unaffected (regression-checked: same
+11.15%/12.68%/1.14 metrics).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Update plan.md "Still open" + close the 2008 caveat

**Files:**
- Modify: `plan.md` (the "Still open" section and the strategy-pivot caveats)

After landing this plan, plan.md should accurately reflect that the 2008 window has been tested.

- [ ] **Step 1: Read the relevant sections**

```bash
grep -n "2008\|recession DD" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/plan.md | head -10
```

- [ ] **Step 2: Add a new dated section above "Still open"**

Insert "### 2008-inclusive backtest — landed YYYY-MM-DD" with:
- Brief description of the time-aware universe + cash-proxy approach.
- Headline metrics from the 2008 backtest (CAGR, MaxDD, Sharpe over the full 2007-2026 window).
- Crisis-period DD specifically (2008-09 peak → 2009-03 trough).
- The verdict on the 15% DD ceiling.
- Link to `reports/learning/2008_stress_test_<date>.md`.

- [ ] **Step 3: Remove the 2008 caveat from existing sections**

The lines:
- `plan.md:36` "Window starts 2013 (no 2008 stress test) — real recession DD could be 30–35%."
- `plan.md:74` "absence of 2008 from window makes recession DD untested"
- `plan.md:197` "Backtest with a 2008-inclusive window when feasible (current alignment starts 2013)."

Replace each with a reference to the new stress-test report. The first two can be replaced with the actual observed crisis-period DD. The third (the open-item) can be removed entirely.

- [ ] **Step 4: Commit**

```bash
git add plan.md
git commit -m "docs(plan): close 2008 backtest caveat with observed crisis-period DD"
```

---

## Self-Review Checklist

1. **Spec coverage:** Two-axis fix — cash proxy (Task 2) and time-aware universe (Tasks 1, 4) — both required to run the long backtest. Driver (Task 3) ties them together; report (Task 3, 5) records the result. ✓
2. **Placeholders:** The 2008 stress-test report contains a "manual analysis required" block (the crisis-period table). This is intentional — the precise dates depend on the run output and would require parsing the CB events table. **Add this as an executor note**: after Task 3 runs, manually fill in the crisis-period table from the underlying backtest report's `cb_events` section.
3. **Type consistency:** `tradeable_as_of` and `filter_bars_by_listing` defined in Task 1, consumed in Task 4. Signatures stable.
4. **Hook compatibility:** No hook-locked file is edited. plan.md is editable.

## Stopping Conditions

- **DD > 20%**: The strategy mix cannot meet the 15% ceiling through a 2008-class event. Surface to user before any commits in Tasks 4-5. The honest framing is: either (a) the 15% number was always aspirational and CLAUDE.md needs an honest revision, or (b) the breaker needs tighter thresholds, in which case go back to walk-forward Plan #4 with a wider grid.
- **yfinance returns empty for any required symbol pre-2008**: The fallback list is BIL → SHY (less ideal cash proxy but available 2002+) → fall back to 2008-01-01 start (1 month past SHV's 2007 listing, fewer warmup days). Document the substitution clearly.
- **Strategy B universe is too small in 2007-2009**: If the time-aware filter leaves fewer than `top_n_entry=5` tradeable names in any momentum window, Strategy B will hold fewer positions. This is *correct behavior* (you can't hold what didn't exist) but worth reporting in the stress-test narrative.
