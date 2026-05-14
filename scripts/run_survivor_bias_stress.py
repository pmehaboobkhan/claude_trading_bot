"""Survivor-bias stress test for Strategy B.

Runs the multi-strategy backtest in 4 configurations:
  1. Modern basket, 2013-2026 (production reference)
  2. As-of basket,  2013-2026 (haircut measurement on production window)
  3. Modern basket, 2007-2026 (extended window — may be truncated by META's
     2012 listing date if alignment is dominated by mid-window IPOs)
  4. As-of basket,  2007-2026 (the most honest forward estimate available)

Configuration 2 vs 1 is the headline haircut (2013-2026 window, apples-to-apples).
Configuration 4 vs 3 extends into the 2008 crisis — but note that the actual
effective start date may be later than 2007 depending on how many anchor symbols
lack pre-2007 data.  The report surfaces the actual effective window.

Usage:
    python3 scripts/run_survivor_bias_stress.py
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

# (label, start, end, universe_mode, cash_proxy)
CONFIGS = [
    ("survivor_modern_2013_2026", "2013-05-24", "2026-05-08", "modern", "SHV"),
    ("survivor_asof_2013_2026",   "2013-05-24", "2026-05-08", "as_of",  "SHV"),
    ("survivor_modern_2007_2026", "2007-06-01", "2026-05-08", "modern", "BIL"),
    ("survivor_asof_2007_2026",   "2007-06-01", "2026-05-08", "as_of",  "BIL"),
]


def _grab(body: str, pattern: str, default: str = "?") -> str:
    m = re.search(pattern, body)
    return m.group(1) if m else default


def _parse_report(path: Path) -> dict:
    """Extract key metrics from a backtest report markdown file."""
    body = path.read_text(encoding="utf-8")
    cagr = _grab(body, r"\*\*Annualized return:\s*([+-]?\d+\.\d+)%\*\*")
    mdd  = _grab(body, r"\*\*Max drawdown:\s*(\d+\.\d+)%\*\*")
    sharpe = _grab(body, r"\*\*Sharpe \(rough\):\s*(\d+\.\d+)\*\*")
    # Per-strategy returns from the allocation table
    strat_b_return = _grab(
        body,
        r"\| large_cap_momentum_top5 \| [^|]+ \| ([+-]?\d+\.\d+)% \|"
    )
    # Actual effective window from the portfolio result
    window_match = re.search(
        r"Multi-strategy backtest — (\S+) → (\S+)", body
    )
    eff_start = window_match.group(1) if window_match else "?"
    eff_end   = window_match.group(2) if window_match else "?"

    return {
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "strat_b_return": strat_b_return,
        "eff_start": eff_start,
        "eff_end": eff_end,
        "report_path": str(path.relative_to(REPO_ROOT)),
    }


def run_one(label: str, start: str, end: str, mode: str, cash: str) -> dict:
    print(f"\n[survivor] running: {label}  ({start} → {end}, mode={mode})")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_multi_strategy_backtest.py"),
        "--start", start,
        "--end",   end,
        "--circuit-breaker",
        "--cash-proxy", cash,
        "--strategy-b-universe-mode", mode,
        "--label", label,
    ]
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=1200)

    # Find the most-recently-written report that contains the label.
    report_dir = REPO_ROOT / "backtests" / "multi_strategy_portfolio"
    candidates = sorted(
        report_dir.glob(f"*{label}*.md"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        print(f"[survivor] FAILED: no report for {label}")
        print("STDOUT:", r.stdout[-2000:])
        print("STDERR:", r.stderr[-1000:])
        return {
            "label": label, "start": start, "end": end,
            "mode": mode, "cash": cash, "error": "no report",
            "cagr": "ERR", "mdd": "ERR", "sharpe": "ERR",
            "strat_b_return": "ERR", "eff_start": "ERR", "eff_end": "ERR",
            "report_path": "N/A",
        }

    metrics = _parse_report(candidates[-1])
    metrics.update({"label": label, "start": start, "end": end, "mode": mode, "cash": cash})
    print(f"  CAGR={metrics['cagr']}%  MaxDD={metrics['mdd']}%  Sharpe={metrics['sharpe']}"
          f"  eff_window={metrics['eff_start']}→{metrics['eff_end']}")
    return metrics


def _try_float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def main() -> int:
    t_start = datetime.utcnow()
    results = [run_one(*cfg) for cfg in CONFIGS]
    elapsed = (datetime.utcnow() - t_start).total_seconds()

    by_label = {r["label"]: r for r in results}

    def cell(label: str, key: str) -> str:
        return by_label.get(label, {}).get(key, "?")

    # Compute haircut deltas
    m2013 = _try_float(cell("survivor_modern_2013_2026", "cagr"))
    a2013 = _try_float(cell("survivor_asof_2013_2026",   "cagr"))
    m2007 = _try_float(cell("survivor_modern_2007_2026", "cagr"))
    a2007 = _try_float(cell("survivor_asof_2007_2026",   "cagr"))

    delta_2013 = (m2013 - a2013) if (m2013 is not None and a2013 is not None) else None
    delta_2007 = (m2007 - a2007) if (m2007 is not None and a2007 is not None) else None

    # Strategy B standalone estimate: ~3.33× portfolio delta (B is 30% of deployed capital)
    # Note: this is only a first-order approximation since A and C returns are unchanged.
    b_standalone_delta_2013 = delta_2013 / 0.30 if delta_2013 is not None else None
    b_standalone_delta_2007 = delta_2007 / 0.30 if delta_2007 is not None else None

    # Haircut assessment
    if delta_2013 is not None:
        if delta_2013 > 2.0:
            haircut_assessment = (
                f"Portfolio CAGR haircut {delta_2013:+.2f}pp/yr EXCEEDS the 2pp trigger. "
                f"Strategy B standalone estimate: ~{b_standalone_delta_2013:+.1f}pp/yr. "
                f"The 60/30/10 allocation was sized assuming a higher Strategy B edge "
                f"than the as-of measurement supports. An allocation review is warranted."
            )
            needs_alloc_review = True
        elif delta_2013 > 0:
            haircut_assessment = (
                f"Portfolio CAGR haircut {delta_2013:+.2f}pp/yr is within the 0-2pp range. "
                f"Strategy B standalone estimate: ~{b_standalone_delta_2013:+.1f}pp/yr. "
                f"The existing plan estimate of 2-4pp/yr at the strategy level is approximately correct."
            )
            needs_alloc_review = False
        else:
            haircut_assessment = (
                f"Portfolio CAGR is HIGHER in as-of mode ({delta_2013:+.2f}pp). "
                f"This is unexpected — check the as-of universe for any pre-collapse names "
                f"whose runs are captured but bankruptcies may be absent from yfinance history."
            )
            needs_alloc_review = False
    else:
        haircut_assessment = "Could not compute haircut (one or both runs failed)."
        needs_alloc_review = False

    today = datetime.utcnow().strftime("%Y-%m-%d")
    out = REPO_ROOT / "reports" / "learning" / f"survivor_bias_stress_{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Survivor-Bias Stress Test for Strategy B — {today}",
        "",
        "## What this measures",
        "",
        "Strategy B's headline returns use the present-day 20-name mega-cap basket.",
        "This basket is the *outcome* of decade-plus market evolution, not the *input* a 2008 trader had.",
        "The as-of basket from `data/historical/sp100_as_of.json` uses a year-by-year point-in-time",
        "S&P 100 membership snapshot — so 2008's universe includes Bear Stearns, Wachovia, AIG;",
        "2009's drops the bankruptcies; 2012 onwards adds META (FB); 2010 onwards adds TSLA; etc.",
        "",
        "## Headline 4-quadrant comparison (full multi-strategy 60/30/10 portfolio)",
        "",
        "| Window (requested) | Effective window | Universe | CAGR | MaxDD | Sharpe |",
        "|---|---|---|---:|---:|---:|",
        f"| 2013-2026 | {cell('survivor_modern_2013_2026', 'eff_start')}→{cell('survivor_modern_2013_2026', 'eff_end')} | modern | {cell('survivor_modern_2013_2026', 'cagr')}% | {cell('survivor_modern_2013_2026', 'mdd')}% | {cell('survivor_modern_2013_2026', 'sharpe')} |",
        f"| 2013-2026 | {cell('survivor_asof_2013_2026', 'eff_start')}→{cell('survivor_asof_2013_2026', 'eff_end')} | as_of  | {cell('survivor_asof_2013_2026', 'cagr')}% | {cell('survivor_asof_2013_2026', 'mdd')}% | {cell('survivor_asof_2013_2026', 'sharpe')} |",
        f"| 2007-2026 | {cell('survivor_modern_2007_2026', 'eff_start')}→{cell('survivor_modern_2007_2026', 'eff_end')} | modern | {cell('survivor_modern_2007_2026', 'cagr')}% | {cell('survivor_modern_2007_2026', 'mdd')}% | {cell('survivor_modern_2007_2026', 'sharpe')} |",
        f"| 2007-2026 | {cell('survivor_asof_2007_2026', 'eff_start')}→{cell('survivor_asof_2007_2026', 'eff_end')} | as_of  | {cell('survivor_asof_2007_2026', 'cagr')}% | {cell('survivor_asof_2007_2026', 'mdd')}% | {cell('survivor_asof_2007_2026', 'sharpe')} |",
        "",
        "**Note on 2007-2026 effective window:** the anchor-symbol alignment drops symbols that lack",
        "data as far back as the requested start.  If the effective window starts significantly later",
        "than 2007-06-01 (e.g., 2013+), the 2007-2026 column does not add meaningful crisis coverage",
        "beyond the 2013-2026 column.  The 2013-2026 column is the primary haircut measurement.",
        "",
        "## Per-strategy B return (from per-strategy allocation table in each report)",
        "",
        "| Window | Universe | Strategy B total return |",
        "|---|---|---:|",
        f"| 2013-2026 | modern | {cell('survivor_modern_2013_2026', 'strat_b_return')}% |",
        f"| 2013-2026 | as_of  | {cell('survivor_asof_2013_2026',   'strat_b_return')}% |",
        f"| 2007-2026 | modern | {cell('survivor_modern_2007_2026', 'strat_b_return')}% |",
        f"| 2007-2026 | as_of  | {cell('survivor_asof_2007_2026',   'strat_b_return')}% |",
        "",
        "(Strategy B standalone CAGR is NOT extracted here — read each report for the full per-strategy",
        "breakdown.  Portfolio-level CAGR delta underestimates Strategy B's haircut by ~3.3× because",
        "Strategies A and C are unchanged across all four runs; only the 30% Strategy B sleeve differs.)",
        "",
        "## Survivor-bias haircut estimate",
        "",
    ]

    if delta_2013 is not None:
        lines += [
            f"- **2013-2026 window (primary):** modern={m2013:.2f}% − as_of={a2013:.2f}% = **{delta_2013:+.2f}pp/yr portfolio haircut**",
            f"  → Strategy B standalone estimate: {delta_2013:.2f} / 0.30 = **~{b_standalone_delta_2013:+.1f}pp/yr**",
        ]
    else:
        lines.append("- 2013-2026 haircut: could not compute (run failed)")

    if delta_2007 is not None:
        lines += [
            f"- **2007-2026 window:** modern={m2007:.2f}% − as_of={a2007:.2f}% = **{delta_2007:+.2f}pp/yr portfolio haircut**",
            f"  → Strategy B standalone estimate: ~{b_standalone_delta_2007:+.1f}pp/yr",
        ]
    else:
        lines.append("- 2007-2026 haircut: could not compute (run failed or effective window collapsed)")

    lines += [
        "",
        f"Plan.md currently estimates a 2-4pp/yr haircut *at the Strategy B level*.",
        f"Measured result (2013-2026, portfolio level): {delta_2013:+.2f}pp/yr" if delta_2013 is not None else "",
        "",
        "## Haircut assessment",
        "",
        haircut_assessment,
        "",
        "Threshold references (from the plan stoppage conditions):",
        "- Portfolio CAGR haircut ≤ 1.5pp/yr → no action needed; commit Task 5 normally.",
        "- Portfolio CAGR haircut > 1.5pp/yr → allocation review flag raised in plan.md.",
        "- Portfolio CAGR haircut > 2.0pp/yr → user notified before committing.",
        "",
        "## Caveats",
        "",
        "- The as-of universe is hand-curated and approximate (mid-year index changes not modeled).",
        "  See `docs/historical_universe_methodology.md`.",
        "- yfinance data for delisted names (Bear Stearns, Wachovia, MER pre-2009) varies.",
        "  Missing bars → symbol skipped by momentum ranker (not tradeable that date).",
        "  This is conservative: it understates the as-of universe's drag.",
        "- The circuit-breaker interacts with portfolio volatility: the as-of run may trigger",
        "  more or fewer CB events depending on the as-of basket's volatility profile.",
        "  Portfolio CAGR delta is therefore a composite of survivor-bias AND CB-interaction effects.",
        "- Strategy B standalone CAGR delta is estimated as portfolio delta / 0.30.  This is a",
        "  first-order approximation that ignores compounding and CB interaction.  Read each report",
        "  for exact per-strategy returns.",
        "",
        "## Backtest reports",
        "",
    ]
    for r in results:
        lines.append(f"- {r['label']}: `{r.get('report_path', 'N/A')}`")

    lines += [
        "",
        f"_Generated by `scripts/run_survivor_bias_stress.py` in {elapsed:.0f}s._",
    ]

    out.write_text("\n".join(l for l in lines) + "\n", encoding="utf-8")
    print(f"\n[survivor] wrote {out.relative_to(REPO_ROOT)}")

    # JSON for downstream tooling
    json_path = out.with_suffix(".json")
    summary = {
        "generated_at": t_start.isoformat() + "Z",
        "elapsed_seconds": round(elapsed),
        "results": results,
        "haircut": {
            "portfolio_cagr_delta_2013_2026": round(delta_2013, 3) if delta_2013 is not None else None,
            "portfolio_cagr_delta_2007_2026": round(delta_2007, 3) if delta_2007 is not None else None,
            "strat_b_standalone_estimate_2013_2026": round(b_standalone_delta_2013, 2) if b_standalone_delta_2013 is not None else None,
            "strat_b_standalone_estimate_2007_2026": round(b_standalone_delta_2007, 2) if b_standalone_delta_2007 is not None else None,
            "needs_allocation_review": needs_alloc_review,
        },
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[survivor] wrote {json_path.relative_to(REPO_ROOT)}")

    if needs_alloc_review:
        print("\n[survivor] WARNING: portfolio haircut exceeds 2pp/yr threshold.")
        print(f"  delta_2013={delta_2013:.2f}pp/yr (portfolio), ~{b_standalone_delta_2013:.1f}pp/yr (Strategy B standalone)")
        print("  Recommendation: surface to user before committing plan.md update.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
