# Survivor-Bias Stress Test on Strategy B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quantify how much of Strategy B's historical edge comes from selecting today's mega-cap winners vs the underlying momentum signal. Re-run Strategy B against a **point-in-time S&P 100 universe** (large-caps as they were at the start of each year) and report the CAGR / MDD / Sharpe haircut.

**Architecture:** Build a static, hand-curated "as-of" universe table — for each year from 2005 onward, list ~30-40 large-cap symbols that were actually in the S&P 100 (or top-30 by market cap) at the start of that year. Strategy B's top-N selection at any given backtest date pulls from the universe active *at that date*, not from a static modern basket. The current modern basket (AAPL, MSFT, …, NVDA) is a curated success list; the as-of basket includes Citi at the start of 2008, GE in 2010, IBM throughout — names that would have been picked but later under-performed or collapsed.

**Tech Stack:** Python 3.12, yfinance (already cached), existing `lib.signals` Strategy B function (consumed unchanged), existing `scripts/run_multi_strategy_backtest.py` machinery.

---

## Why this matters (one paragraph for the executor)

Strategy B's standalone +2005% over 13 years (per `plan.md:42`) is impressive — and at least partially fake. The 20-name "modern mega-cap" basket is the *outcome* of 13 years of evolution, not the *input*. A trader in 2013 didn't know AAPL/NVDA/META would dominate; they had to pick from the actual large-cap basket of 2013, which included names like Cisco, IBM, GE, and Exxon trading at very different positions. The plan currently estimates a 2-4pp/yr haircut from survivor bias ([plan.md:42](../../plan.md:42)). That estimate is hand-waved. This plan replaces the estimate with measured evidence: we re-run Strategy B against a year-by-year point-in-time universe and report the actual CAGR delta. If the haircut is much larger than 4pp/yr (e.g., +20% real vs +180% biased), the realistic forward expectation for Strategy B is much weaker than the production allocation assumes.

---

## File Structure

**Create:**
- `data/historical/sp100_as_of.json` — hand-curated mapping `{year_iso → [symbols]}` for 2005-2026.
- `lib/historical_membership.py` — pure helpers: `members_as_of(date)`, `validate_universe()`.
- `tests/test_historical_membership.py` — pure tests.
- `scripts/run_survivor_bias_stress.py` — driver that runs Strategy B twice (modern basket vs as-of) and writes a comparison.
- `reports/learning/survivor_bias_stress_<date>.md` — comparison report.
- `docs/historical_universe_methodology.md` — documents how the as-of table was assembled (sources, definitions, known gaps).

**Modify:**
- `scripts/run_multi_strategy_backtest.py` — add `--strategy-b-universe-mode <modern|as_of>` flag. Default unchanged (`modern`). When `as_of`, the script swaps in the time-varying universe.

**No edits to:**
- `lib/signals.py` Strategy B function — it consumes whatever `bars_by_symbol` it's given.
- Any production config or prompt.

---

## Methodology — read before writing the universe table

Survivor bias creeps in via three mechanisms:

1. **Listing-date bias** — handled by `lib/historical_universe.py` from the 2008-backtest plan. META wasn't tradeable in 2008.
2. **Membership bias** — what we're fixing here. The S&P 100 in 2008 included names that have since been removed (Lehman, Bear Stearns, Wachovia, Sun Microsystems, Compaq, etc.). Building a membership table over time corrects this.
3. **Index-rebalance bias** — point-in-time data on actual S&P 100 membership is paywalled (most quant data vendors charge for it). We approximate using publicly available year-end S&P 100 lists from Wikipedia archives + cross-checked against SEC filings for the largest names.

**Honest scope of this plan:** the as-of universe is *approximate*. We're not trying to perfectly reconstruct historical index membership; we're trying to demonstrate the *order of magnitude* of the survivor bias by including a handful of names per year that were prominent then but irrelevant or delisted now. That's enough to measure the haircut.

---

## Task 1: Hand-curate the year-by-year S&P 100 as-of universe

**Files:**
- Create: `data/historical/sp100_as_of.json`
- Create: `docs/historical_universe_methodology.md`

This is human-judgment work, not code work. The JSON file is a static lookup — once curated, it's append-only as new years are added.

- [ ] **Step 1: Create the methodology doc**

```markdown
# Historical Universe Methodology

## Purpose
Replace Strategy B's modern-basket survivor-biased universe with a year-by-year approximation of the actual S&P 100 (or top-30 by market cap) membership. Used by `scripts/run_survivor_bias_stress.py` to produce an honest measurement of the survivor-bias haircut.

## Data structure
`data/historical/sp100_as_of.json`:
```json
{
  "2005": ["AAPL", "MSFT", "INTC", "CSCO", "GE", "XOM", "WMT", "C", "BAC", "JNJ", ...],
  "2006": [...],
  ...
  "2026": [...]
}
```

The list for year YYYY is the universe active for the entire calendar year YYYY. Strategy B's top-N selection at date D uses the list for `year(D)`.

## Sources
- Wikipedia "S&P 100 Index" article history (revision dates near each year-end).
- StockAnalysis.com / Slickcharts archived S&P 100 lists.
- SEC 10-K filings for individual names (to confirm a name was operating + listed in a given year).
- Cross-check against yfinance: every symbol in the table MUST have bars covering at least the year(s) it appears in.

## Known approximations
- Index changes mid-year are NOT modeled. A symbol added in July 2010 is treated as either present or absent for all of 2010 — typically we treat it as **absent** that year (conservative).
- Symbols that were renamed (e.g., FB → META, GOOG → GOOGL share class) are treated using the symbol that was active that year.
- Mergers (e.g., XOM + Mobil = XOM; PFE + Wyeth = PFE; T + BLS = T) use the surviving ticker.
- Bankruptcies (Lehman 2008-09, GM 2009-06, Citi rescue) are **important to include** for the year(s) they were in the index, even if they were later removed. The whole point of this exercise is that a 2008-vintage portfolio might have held them.

## Validation rule
For each year Y: every symbol in the list must have at least one yfinance bar dated YYYY-01-15 ± 30 days. Run `lib.historical_membership.validate_universe()` after every edit.
```

- [ ] **Step 2: Curate the JSON file**

This is the actual hand work. Create `data/historical/sp100_as_of.json` with one entry per year from 2005 to 2026. Use the methodology above. Aim for ~30-40 names per year (top of S&P 100 plus a few then-prominent names).

Rough year-by-year guidance:

```json
{
  "2005": [
    "AAPL", "MSFT", "INTC", "CSCO", "ORCL", "DELL", "HPQ", "IBM", "TXN", "AMZN",
    "GE", "XOM", "CVX", "COP", "WMT", "HD", "TGT", "COST", "MCD",
    "JPM", "C", "BAC", "WFC", "MER", "AIG", "GS", "MS",
    "JNJ", "PFE", "MRK", "ABT", "BMY", "LLY",
    "KO", "PEP", "PG", "PM", "MO",
    "T", "VZ", "S", "BLS",
    "F", "GM", "CAT", "BA", "GD", "HON",
    "NEM", "UTX", "WAG", "DD"
  ],
  "2006": ["...", "GOOG"],
  "2007": ["..."],
  "2008": [
    "AAPL", "MSFT", "GOOG", "ORCL", "INTC", "CSCO", "IBM", "HPQ", "DELL", "AMZN",
    "GE", "XOM", "CVX", "COP", "WMT", "HD", "TGT", "COST", "MCD",
    "JPM", "C", "BAC", "WFC", "GS", "MS", "AIG", "MER", "LEH", "BSC", "WB",
    "JNJ", "PFE", "MRK", "ABT", "BMY", "LLY",
    "KO", "PEP", "PG", "MO",
    "T", "VZ",
    "F", "GM", "CAT", "BA",
    "V"
  ],
  "...": "..."
}
```

(The above is a *starting template*; the actual curation requires checking historical Wikipedia revisions. **Allocate at least 2 hours for this step.**)

- [ ] **Step 3: Sanity check yourself**

For each year YYYY:
- Total entries should be ~30-40, not 5 and not 80.
- 2008 should include Lehman (LEH), Bear Stearns (BSC), Wachovia (WB), Merrill (MER), AIG. These get removed in 2009-2010 lists.
- 2010 onwards should drop GM (bankruptcy reorg) and Citigroup (delisting + reverse split), or note them with the new tickers.
- 2012 should add META (FB).
- 2010 should add TSLA.
- 2014 onwards should distinguish GOOGL vs GOOG (share-class split).

- [ ] **Step 4: Commit (the JSON + methodology together)**

```bash
git add data/historical/sp100_as_of.json docs/historical_universe_methodology.md
git commit -m "data: hand-curated S&P 100 as-of universe 2005-2026

Year-by-year approximation of S&P 100 membership for survivor-bias
correction. Methodology + sources documented in
docs/historical_universe_methodology.md. Approximate (mid-year
rebalances not modeled) but sufficient to measure the haircut.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Implement `lib/historical_membership.py`

**Files:**
- Create: `lib/historical_membership.py`
- Create: `tests/test_historical_membership.py`

Pure helpers that load the JSON and answer "what was in the universe on date X".

- [ ] **Step 1: Write failing tests**

```python
# tests/test_historical_membership.py
"""Pure tests for lib.historical_membership."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import historical_membership as hm  # noqa: E402


def test_members_as_of_uses_year_of_date(tmp_path):
    path = tmp_path / "sp100.json"
    path.write_text(json.dumps({
        "2008": ["LEH", "AIG", "AAPL"],
        "2009": ["AIG", "AAPL"],  # LEH removed
        "2010": ["AAPL", "TSLA"],
    }))
    assert sorted(hm.members_as_of("2008-09-15", path=path)) == ["AAPL", "AIG", "LEH"]
    assert sorted(hm.members_as_of("2009-03-01", path=path)) == ["AAPL", "AIG"]
    assert sorted(hm.members_as_of("2010-12-31", path=path)) == ["AAPL", "TSLA"]


def test_members_as_of_unknown_year_returns_nearest_prior(tmp_path):
    path = tmp_path / "sp100.json"
    path.write_text(json.dumps({
        "2010": ["AAPL", "TSLA"],
        "2015": ["AAPL", "TSLA", "META"],
    }))
    # Years between known anchors fall back to the most recent prior anchor.
    assert sorted(hm.members_as_of("2012-06-01", path=path)) == ["AAPL", "TSLA"]
    # Years before the earliest anchor raise.
    import pytest
    with pytest.raises(ValueError, match="before earliest"):
        hm.members_as_of("2005-01-01", path=path)


def test_validate_universe_passes_when_all_symbols_have_yfinance_data(tmp_path):
    """validate_universe is a stub here — full check requires yfinance.

    The pure-helper version just checks file structure (every key is a
    YYYY string; every value is a non-empty list of uppercase strings).
    Full data-availability check is in scripts/run_survivor_bias_stress.py.
    """
    path = tmp_path / "sp100.json"
    path.write_text(json.dumps({"2010": ["AAPL", "MSFT"]}))
    issues = hm.validate_universe(path=path)
    assert issues == []


def test_validate_universe_flags_lowercase_and_empty():
    """Detects malformed entries."""
    import json
    p = Path("/tmp") / "_bad_sp100.json"
    p.write_text(json.dumps({
        "2010": ["aapl", "MSFT"],   # lowercase
        "20xx": ["AAPL"],            # bad year key
        "2011": [],                  # empty
    }))
    issues = hm.validate_universe(path=p)
    p.unlink()
    assert len(issues) == 3
    issue_text = " ".join(issues)
    assert "lowercase" in issue_text or "uppercase" in issue_text
    assert "year" in issue_text
    assert "empty" in issue_text
```

- [ ] **Step 2: Run tests to see them fail**

```bash
python3 -m pytest tests/test_historical_membership.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `lib/historical_membership.py`**

```python
# lib/historical_membership.py
"""Point-in-time S&P 100 membership lookup.

Reads data/historical/sp100_as_of.json (year → [symbols]) and
answers `members_as_of(date_iso)`. Used by the survivor-bias stress
test to feed Strategy B a year-appropriate universe instead of the
modern winners basket.

The JSON file is hand-curated; see docs/historical_universe_methodology.md.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "data" / "historical" / "sp100_as_of.json"


def _load(path: Path | None = None) -> dict[str, list[str]]:
    p = path or DEFAULT_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def members_as_of(date_iso: str, *, path: Path | None = None) -> list[str]:
    """Return the universe active on the given date.

    Strategy: take the entry for `year(date_iso)`. If that year is missing,
    fall back to the most recent prior year. Raises ValueError if the
    date is before the earliest year in the table.
    """
    table = _load(path)
    year_str = date_iso[:4]
    if year_str in table:
        return list(table[year_str])
    # Fall back to most recent prior anchor
    available = sorted(int(y) for y in table.keys() if y.isdigit())
    if not available:
        raise ValueError("empty universe table")
    target = int(year_str)
    priors = [y for y in available if y <= target]
    if not priors:
        earliest = min(available)
        raise ValueError(f"date {date_iso} is before earliest universe year {earliest}")
    return list(table[str(priors[-1])])


def all_known_symbols(*, path: Path | None = None) -> list[str]:
    """Union of every symbol that appears in any year of the table.

    Used by the script to build the bar-fetch list — fetch once, slice per-year.
    """
    table = _load(path)
    out: set[str] = set()
    for syms in table.values():
        out.update(syms)
    return sorted(out)


def validate_universe(*, path: Path | None = None) -> list[str]:
    """Structural validation. Returns list of issue strings (empty = OK).

    Checks:
    - Every key is a 4-digit year string
    - Every value is a non-empty list
    - Every symbol is uppercase ASCII
    """
    issues: list[str] = []
    table = _load(path)
    for key, syms in table.items():
        if not (key.isdigit() and len(key) == 4):
            issues.append(f"bad year key: '{key}' (must be 4-digit YYYY)")
            continue
        if not syms:
            issues.append(f"empty universe for year {key}")
            continue
        for s in syms:
            if not isinstance(s, str) or not s.isascii() or not s.isupper():
                issues.append(f"symbol '{s}' in year {key} must be uppercase ASCII")
    return issues
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_historical_membership.py -v
```
Expected: 4 PASS.

- [ ] **Step 5: Validate the curated JSON**

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from lib import historical_membership as hm
issues = hm.validate_universe()
if issues:
    print('VALIDATION ISSUES:')
    for i in issues: print(f'  - {i}')
    sys.exit(1)
print('OK; total years:', len(hm._load()))
print('Universe size in 2008:', len(hm.members_as_of('2008-06-30')))
print('Universe size in 2026:', len(hm.members_as_of('2026-01-15')))
print('Total unique symbols across all years:', len(hm.all_known_symbols()))
"
```
Expected: `OK; total years: 22`, universe sizes ~30-40 each year, total unique symbols 60-100 across all years.

- [ ] **Step 6: Commit**

```bash
git add lib/historical_membership.py tests/test_historical_membership.py
git commit -m "feat: historical S&P 100 membership lookup

Pure helper that reads data/historical/sp100_as_of.json and answers
'what was in the universe on date X'. Strategy: exact year match,
falling back to nearest prior. Validation on file structure included.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Strategy B universe-mode flag in the backtest script

**Files:**
- Modify: `scripts/run_multi_strategy_backtest.py`

The Strategy B function in `lib.signals` consumes whatever `bars_by_symbol` it gets. To run it with an as-of universe, we need to vary the bars-dict per-date. Easiest implementation: at each rebalance date, slice the full bars-dict to only include symbols active in that year. The Strategy B momentum-rank computation will only consider those symbols.

But Strategy B's existing implementation evaluates on the full universe at each tick. Restructuring that is invasive. **Cleaner alternative:** run the backtest with the as-of UNION of all years' symbols (so all bars are fetched), and apply a per-date filter inside a small wrapper that we plug into the backtest at the right point.

Look at how `run_multi_strategy_backtest.py` invokes Strategy B; the cleanest insertion point depends on the existing structure.

- [ ] **Step 1: Find where Strategy B is invoked**

```bash
grep -n "evaluate_large_cap_momentum_top5\|large_cap_momentum_top5\|STRATEGY_FUNCS" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/scripts/run_multi_strategy_backtest.py | head -10
grep -n "evaluate_large_cap_momentum_top5" /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/lib/backtest.py | head -10
```

Note the entry point. If `lib.backtest` calls `signals.evaluate_large_cap_momentum_top5(bars_by_symbol, ...)` once per rebalance date, the cleanest fix is to wrap that call.

- [ ] **Step 2: Add `--strategy-b-universe-mode` flag + wrapper**

In `scripts/run_multi_strategy_backtest.py`:

```python
parser.add_argument("--strategy-b-universe-mode", default="modern",
                    choices=["modern", "as_of"],
                    help="'modern' uses the present-day mega-cap basket from "
                         "watchlist.yaml. 'as_of' uses lib/historical_membership.py "
                         "to apply a year-by-year point-in-time universe (used by "
                         "the survivor-bias stress test).")
```

Where Strategy B's bars dict is constructed (or where its universe is selected), wrap with:

```python
from lib import historical_membership

def universe_for_date(date_iso: str) -> set[str] | None:
    """Return the symbol set Strategy B may consider on date_iso.

    None means 'no restriction' (modern mode). A set means 'only these'.
    """
    if args.strategy_b_universe_mode == "modern":
        return None
    return set(historical_membership.members_as_of(date_iso))
```

Then at every rebalance step inside Strategy B's call site:

```python
allowed = universe_for_date(rebalance_date)
if allowed is not None:
    bars_for_b = {sym: bars for sym, bars in all_bars.items() if sym in allowed}
else:
    bars_for_b = all_bars
# now call evaluate_large_cap_momentum_top5(bars_for_b, ...)
```

(The exact wiring depends on how `lib.backtest` integrates with strategy functions. If the function is invoked once with a static `bars_by_symbol` and produces a list of signals across the whole window, you'll need to instead drive Strategy B in a per-rebalance-date loop. Look at what the script already does for the 2008-backtest plan's listing-filter — same insertion point.)

- [ ] **Step 3: Verify modern-mode still produces unchanged results**

```bash
python3 scripts/run_multi_strategy_backtest.py --start 2013-05-24 --end 2026-05-08 --circuit-breaker --label survivor_modern_check
```
Expected: same +11.15% / 12.68% / 1.14 metrics as the production reference.

- [ ] **Step 4: Run with as_of universe (still 2013-2026 window first as a sanity check)**

```bash
python3 scripts/run_multi_strategy_backtest.py --start 2013-05-24 --end 2026-05-08 --circuit-breaker --strategy-b-universe-mode as_of --label survivor_asof_check
```
Expected: completes; Strategy B's CAGR is materially lower (the as-of basket includes IBM, GE, GS, etc. that under-performed). The 2013+ window is benign — the bigger delta will show in the 2008-inclusive window in Task 4.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_multi_strategy_backtest.py
git commit -m "feat(backtest): --strategy-b-universe-mode {modern|as_of}

'modern' (default, unchanged): present-day watchlist mega-caps.
'as_of': year-by-year point-in-time S&P 100 membership from
data/historical/sp100_as_of.json. Drives the survivor-bias
stress test.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Survivor-bias stress test driver + comparison report

**Files:**
- Create: `scripts/run_survivor_bias_stress.py`

Runs the multi-strategy backtest twice (modern vs as_of), once for the production window and once for the 2008-inclusive window, and writes a 4-quadrant comparison.

- [ ] **Step 1: Build the script**

```python
# scripts/run_survivor_bias_stress.py
"""Survivor-bias stress test for Strategy B.

Runs the multi-strategy backtest in 4 configurations:
  1. Modern basket, 2013-2026 (production reference)
  2. As-of basket,  2013-2026 (haircut measurement on production window)
  3. Modern basket, 2007-2026 (8-year extension on biased basket)
  4. As-of basket,  2007-2026 (the most honest forward estimate available)

Configuration 4 is the headline number. Compare its CAGR to (1) — that
delta is the realistic survivor-bias haircut for Strategy B.

Usage:
    python scripts/run_survivor_bias_stress.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CONFIGS = [
    # (label, start, end, universe_mode, cash_proxy)
    ("survivor_modern_2013_2026", "2013-05-24", "2026-05-08", "modern", "SHV"),
    ("survivor_asof_2013_2026",   "2013-05-24", "2026-05-08", "as_of", "SHV"),
    ("survivor_modern_2007_2026", "2007-06-01", "2026-05-08", "modern", "BIL"),
    ("survivor_asof_2007_2026",   "2007-06-01", "2026-05-08", "as_of",  "BIL"),
]


def run_one(label: str, start: str, end: str, mode: str, cash: str) -> dict:
    print(f"\n[survivor] running: {label}")
    cmd = [
        sys.executable, str(REPO_ROOT / "scripts" / "run_multi_strategy_backtest.py"),
        "--start", start, "--end", end,
        "--circuit-breaker",
        "--cash-proxy", cash,
        "--strategy-b-universe-mode", mode,
        "--label", label,
    ]
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    # Find the report file
    candidates = sorted((REPO_ROOT / "backtests" / "multi_strategy_portfolio").glob(f"*{label}*.md"),
                        key=lambda p: p.stat().st_mtime)
    if not candidates:
        print(f"[survivor] FAILED to find report for {label}")
        print("STDOUT:", r.stdout[-1000:])
        print("STDERR:", r.stderr[-1000:])
        return {"label": label, "error": "no report"}

    body = candidates[-1].read_text(encoding="utf-8")
    def grab(pattern: str, default: str = "?") -> str:
        m = re.search(pattern, body)
        return m.group(1) if m else default

    return {
        "label": label,
        "start": start, "end": end, "mode": mode, "cash": cash,
        "cagr": grab(r"Annualized.*?\|\s*([+-]?\d+\.\d+)%"),
        "mdd": grab(r"Max drawdown.*?\|\s*(\d+\.\d+)%"),
        "sharpe": grab(r"Sharpe.*?\|\s*(\d+\.\d+)"),
        "report_path": str(candidates[-1].relative_to(REPO_ROOT)),
    }


def main() -> int:
    results = [run_one(*cfg) for cfg in CONFIGS]

    out = REPO_ROOT / "reports" / "learning" / (
        f"survivor_bias_stress_{datetime.utcnow():%Y-%m-%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    # Build the 4-quadrant table
    by_label = {r["label"]: r for r in results}
    def cell(label, key):
        v = by_label.get(label, {}).get(key, "?")
        return v

    lines = [
        f"# Survivor-Bias Stress Test for Strategy B — {datetime.utcnow():%Y-%m-%d}",
        "",
        "## What this measures",
        "",
        "Strategy B's headline returns use the present-day 20-name mega-cap basket.",
        "This basket is the *outcome* of decade-plus market evolution, not the *input* a 2008 trader had.",
        "The as-of basket from `data/historical/sp100_as_of.json` uses a year-by-year point-in-time",
        "S&P 100 membership snapshot — so 2008's universe includes Lehman, Bear Stearns, Wachovia, AIG;",
        "2010's drops the bankruptcies; 2012 onwards adds META; 2010 onwards adds TSLA; etc.",
        "",
        "## Headline 4-quadrant comparison (full multi-strategy 60/30/10 portfolio)",
        "",
        "| Window | Universe | CAGR | MaxDD | Sharpe |",
        "|---|---|---:|---:|---:|",
        f"| 2013-2026 | modern   | {cell('survivor_modern_2013_2026', 'cagr')}% | {cell('survivor_modern_2013_2026', 'mdd')}% | {cell('survivor_modern_2013_2026', 'sharpe')} |",
        f"| 2013-2026 | as_of    | {cell('survivor_asof_2013_2026', 'cagr')}% | {cell('survivor_asof_2013_2026', 'mdd')}% | {cell('survivor_asof_2013_2026', 'sharpe')} |",
        f"| 2007-2026 | modern   | {cell('survivor_modern_2007_2026', 'cagr')}% | {cell('survivor_modern_2007_2026', 'mdd')}% | {cell('survivor_modern_2007_2026', 'sharpe')} |",
        f"| 2007-2026 | as_of    | {cell('survivor_asof_2007_2026', 'cagr')}% | {cell('survivor_asof_2007_2026', 'mdd')}% | {cell('survivor_asof_2007_2026', 'sharpe')} |",
        "",
        "## Survivor-bias haircut estimate",
        "",
        "Compute the CAGR delta:",
        "",
        f"- 2013-2026 window: modern ({cell('survivor_modern_2013_2026', 'cagr')}%) − as_of ({cell('survivor_asof_2013_2026', 'cagr')}%)",
        f"- 2007-2026 window: modern ({cell('survivor_modern_2007_2026', 'cagr')}%) − as_of ({cell('survivor_asof_2007_2026', 'cagr')}%)",
        "",
        "Plan.md currently estimates a 2-4pp/yr haircut. Compare to the deltas above:",
        "- Delta ≤ 4pp/yr → existing estimate was approximately right; no plan changes needed.",
        "- Delta 4-8pp/yr → plan estimate is optimistic; update to reflect.",
        "- Delta > 8pp/yr → Strategy B's edge is largely artifactual; recommend reviewing",
        "  its 30% portfolio allocation (the 60/30/10 split was justified by an inflated edge).",
        "",
        "## Strategy B standalone CAGR (extracted from each backtest report's per-strategy table)",
        "",
        "*Manual analysis required.* Open each report file and find the per-strategy table:",
        "",
        "| Window | Universe | Strategy B standalone CAGR |",
        "|---|---|---:|",
        f"| 2013-2026 | modern   | TBD (read {cell('survivor_modern_2013_2026', 'report_path')}) |",
        f"| 2013-2026 | as_of    | TBD (read {cell('survivor_asof_2013_2026', 'report_path')}) |",
        f"| 2007-2026 | modern   | TBD (read {cell('survivor_modern_2007_2026', 'report_path')}) |",
        f"| 2007-2026 | as_of    | TBD (read {cell('survivor_asof_2007_2026', 'report_path')}) |",
        "",
        "(The portfolio-level CAGR delta dilutes Strategy B's signal because Strategies A and C are",
        "unchanged across all four runs — only the 30% Strategy B sleeve differs. Strategy B's",
        "standalone CAGR delta is ~3.3× the portfolio-level delta.)",
        "",
        "## Caveats",
        "",
        "- The as-of universe is hand-curated and approximate. Mid-year index changes are not modeled.",
        "  See `docs/historical_universe_methodology.md`.",
        "- We approximate S&P 100 membership; the actual production strategy uses a smaller curated list.",
        "  The relevant question is not 'which exact symbols' but 'how big is the haircut from picking",
        "  out of a then-realistic large-cap basket vs the modern winners'.",
        "- yfinance bar quality for delisted names (Lehman, Wachovia, etc.) varies — some have full",
        "  history through bankruptcy, others end abruptly. The script should treat missing bars as",
        "  'symbol not tradeable on that date' (Strategy B's existing logic handles this — it skips",
        "  symbols without enough momentum-window history).",
        "- Bankruptcy-induced -100% returns are *real* edge cases. If a held name goes to zero, that is",
        "  the genuine outcome a 2008 portfolio would have suffered. The backtest should NOT shield",
        "  this; that's the whole point.",
        "",
        "## Backtest reports (for deeper inspection)",
        "",
    ]
    for r in results:
        lines.append(f"- {r['label']}: `{r.get('report_path', 'N/A')}`")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[survivor] wrote {out.relative_to(REPO_ROOT)}")

    # Also emit a JSON of raw numbers for downstream tooling
    json_path = out.with_suffix(".json")
    json_path.write_text(json.dumps(results, indent=2))
    print(f"[survivor] wrote {json_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the stress test**

```bash
python3 scripts/run_survivor_bias_stress.py
```
Expected: 4 backtests run sequentially (~5-15 min total); two reports produced (markdown + json) under `reports/learning/`.

- [ ] **Step 3: Read the headline numbers**

```bash
cat /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/reports/learning/survivor_bias_stress_*.md | head -40
```

Compute the haircut deltas yourself and surface to the user. Specifically:
- 2013-2026 modern minus 2013-2026 as_of = portfolio-level haircut on the production window.
- 2007-2026 modern minus 2007-2026 as_of = portfolio-level haircut including the crisis.
- Multiply the portfolio-level deltas by ~3.3 to estimate Strategy B's *standalone* haircut (since B is 30% of the portfolio).

- [ ] **Step 4: Decide whether to commit or escalate**

- If portfolio CAGR haircut ≤ 1pp (Strategy B haircut ≤ 3.3pp/yr) → existing 2-4pp/yr plan estimate was approximately right. Continue to Task 5 to update plan.md.
- If portfolio CAGR haircut > 1.5pp (Strategy B haircut > 5pp/yr) → plan.md significantly underestimated the haircut. **Stop and surface to user**. The 60/30/10 allocation may need revisiting.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_survivor_bias_stress.py reports/learning/survivor_bias_stress_*.md reports/learning/survivor_bias_stress_*.json
git commit -m "research: survivor-bias stress test for Strategy B

Runs 4-quadrant comparison (modern vs as_of × 2013-2026 vs 2007-2026)
to measure how much of Strategy B's edge comes from selecting today's
mega-cap winners vs the underlying momentum signal.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Update plan.md survivor-bias note with measured haircut

**Files:**
- Modify: `plan.md` (lines 41-42 and 74)

The current plan claims a 2-4pp/yr haircut. Replace with measured numbers.

- [ ] **Step 1: Read the current caveat block**

```bash
sed -n '40,45p' /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/plan.md
sed -n '72,76p' /Users/mehaboob.khan.perur/gitrepos/claude_trading_bot/plan.md
```

- [ ] **Step 2: Edit the survivor-bias caveat**

Replace the existing text with measured findings. Example shape (substitute the actual numbers from your run):

```
### Survivor bias caveat (measured 2026-05-XX)

Strategy B's standalone +2005% (13y) is inflated by selecting today's mega-cap survivors. **Measured haircut from the survivor-bias stress test (`reports/learning/survivor_bias_stress_<date>.md`): X.X pp/yr at the portfolio level, ≈ Y.Y pp/yr for Strategy B standalone.** Realistic forward estimate after haircut: ~Z-W% annualized for Strategy B. The as-of universe substitution methodology is documented in `docs/historical_universe_methodology.md`.

The 60/30/10 allocation was sized assuming a higher Strategy B edge than the as-of measurement supports. <One sentence on whether this is acceptable, requires re-allocation, or has been deferred to a future review.>
```

- [ ] **Step 3: Add a "Still open" item if a re-allocation review is warranted**

If the haircut is large enough that the 60/30/10 split should be revisited, add to the "Still open" list:

```
- [ ] Strategy B allocation review: measured survivor-bias haircut of ~Y.Y pp/yr suggests Strategy B's allocated capital may need to drop from 30% (e.g., to 15-20%, with the freed allocation moving to gold or cash). Pending: re-run the multi-strategy backtest with revised allocations and confirm the 8-10% / 15% DD / Sharpe ≥ 0.8 targets still pass.
```

- [ ] **Step 4: Commit**

```bash
git add plan.md
git commit -m "docs(plan): replace estimated survivor-bias haircut with measured numbers

Stress test in reports/learning/survivor_bias_stress_<date>.md
produces measured per-year CAGR delta on Strategy B; plan now
references the actual numbers and (if applicable) flags the
allocation question for review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - As-of universe data: Task 1 (JSON + methodology). ✓
   - Lookup helper: Task 2. ✓
   - Backtest plumbing: Task 3 (CLI flag + per-date filter). ✓
   - Stress test driver: Task 4. ✓
   - Plan update: Task 5. ✓
2. **Placeholders:** Two intentional ones:
   - The JSON template in Task 1 Step 2 has only 2008 fully spelled out; the executor must do the curation work for the other years. This is human judgment and cannot be automated.
   - The Task 4 report has a "TBD (read report path)" line for Strategy B standalone CAGR — extracting that from the report requires parsing the per-strategy table; left manual to keep the script simple.
3. **Type consistency:** `members_as_of(date_iso)` returns `list[str]` consistently; consumed by the script as a set comprehension.
4. **Hook compatibility:** No PR-locked file is edited (the script consumes the watchlist via the `--strategy-b-universe-mode` flag without modifying it). plan.md is editable.

## Stopping Conditions

- **JSON validation fails (Task 2 Step 5)**: fix the entries flagged before proceeding. The full pipeline depends on the file being well-formed.
- **as_of run produces wildly higher CAGR than modern**: this would mean the as-of basket includes high-flying delisted names whose late-stage runs are captured but eventual collapses aren't. Re-check the universe for symbols that were *delisted by acquisition* (where yfinance shows just the run-up) and ensure bankruptcies are represented.
- **Portfolio-level haircut > 2pp/yr**: very strong signal that the 60/30/10 allocation needs review. Surface to user before any commit; the plan.md update should reflect that an allocation review is required, not just record the number.
- **The 2007-2026 as_of run produces a max DD over 25%**: this would mean the as-of basket through the 2008 crisis is much rougher than the modern basket suggests. Cross-link to the 2008-backtest plan's results — both speak to the same underlying question (how does the system behave under crisis stress).
