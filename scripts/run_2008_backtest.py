"""Long-window backtest including the 2007-2009 financial crisis.

Standard backtest starts 2013-05-24. This one starts 2007-06-01 (giving
6 months warmup for the 10-month SMA filter before any signals fire,
so first real trades are around 2008-04). Uses BIL as cash proxy
(SHV's data is thinner in early 2007) and the anchor-based alignment
that correctly handles mid-window IPOs (META 2012, TSLA 2010, V 2008).

Architecture note: `align_bars()` in run_multi_strategy_backtest.py was
updated to use anchor-based alignment: only symbols with data back to
args.start define the common trading-date grid. Mid-window IPOs are merged
onto this grid with empty bars in early years, letting signals.py's
momentum-window gate exclude them until they have enough history.

Usage:
    python scripts/run_2008_backtest.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_multi_strategy_backtest as bt_mod  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2007-06-01",
                        help="Backtest start. BIL data begins 2007-05-30 so use 2007-06-01 "
                             "or later. Strategy A warmup is 252 trading days (~12 months); "
                             "first real signals fire around 2008-06.")
    parser.add_argument("--end", default="2026-05-08")
    parser.add_argument("--cash-proxy", default="BIL", choices=["SHV", "BIL", "SHY"])
    parser.add_argument("--label", default="2008_inclusive")
    args = parser.parse_args()

    print(f"[2008-bt] 2008-inclusive backtest")
    print(f"[2008-bt] start={args.start} end={args.end} cash_proxy={args.cash_proxy}")

    # Run in-process (no subprocess) — faster and avoids permission issues.
    bt_args = SimpleNamespace(
        start=args.start,
        end=args.end,
        capital=100_000.0,
        alloc_a=0.60,
        alloc_b=0.30,
        alloc_c=0.10,
        cash_buffer_pct=0.0,
        cash_proxy=args.cash_proxy,
        circuit_breaker=True,
        cb_half_dd=0.08,
        cb_out_dd=0.12,
        cb_recovery_dd=0.05,
        cb_out_recover_dd=0.08,
        sma_months=10,
        label=args.label,
        write_report=True,
    )
    result = bt_mod.run_backtest(bt_args)

    cagr = f"{result['ann_return']:.2f}"
    mdd = f"{result['max_drawdown_pct']:.2f}"
    sharpe = f"{result['sharpe']:.2f}"
    n_events = str(len(result.get("cb_events", [])))

    # Compose the recession-focused stress-test report.
    out = REPO_ROOT / "reports" / "learning" / (
        f"2008_stress_test_{datetime.utcnow():%Y-%m-%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    # Find the produced report file
    report_dir = REPO_ROOT / "backtests" / "multi_strategy_portfolio"
    candidates = sorted(report_dir.glob(f"*{args.label}*.md"), key=lambda p: p.stat().st_mtime)
    backtest_report_path = candidates[-1] if candidates else report_dir / f"unknown_{args.label}.md"

    lines = [
        f"# 2008-Inclusive Stress Test — {datetime.utcnow():%Y-%m-%d}",
        "",
        f"Window: {args.start} → {args.end} (~{(int(args.end[:4]) - int(args.start[:4]))}y)",
        f"Cash proxy: {args.cash_proxy}",
        f"Strategy B universe: time-aware via `lib.historical_universe` (anchor-based alignment)",
        f"Underlying backtest report: `{backtest_report_path.relative_to(REPO_ROOT)}`",
        "",
        "## Architecture note: anchor-based alignment",
        "",
        "The `run_multi_strategy_backtest.py` was updated to use anchor-based alignment.",
        "Only symbols with data back to `args.start` define the common trading-date grid.",
        "Mid-window IPOs (META 2012, TSLA 2010, V 2008) are merged onto this grid with",
        "empty bars in early years — `signals.py` naturally excludes them from top-N",
        "selection until they accumulate `momentum_window_days` (126) of history.",
        "This fixes the prior issue where `align_bars()` would snap the entire window",
        "to 2013 because META's first bar is 2012-05-18.",
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
        "| Metric | 2013-2026 (prod, SHV) | 2007-2026 (this run) | Delta |",
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
        "- The maximum drawdown depth during 2008-09 → 2009-03 specifically",
        "- Recovery time from trough to new high (calendar months)",
        "- Which strategy was hit hardest (likely Strategy B momentum during the crash)",
        "- Whether the circuit-breaker engaged early (FULL→HALF at -8% in late 2008)",
        "  or late (the value of the breaker depends on its responsiveness here)",
        "",
        "Fill the table below by reading the backtest's CB events table:",
        "",
        "| Date | Event | Portfolio % from peak |",
        "|---|---|---:|",
        "| 2007-10-09 | SPY all-time-high (start of crisis) | 0.0% |",
        "| 2008-XX-XX | First FULL→HALF transition (when?) | TBD — read CB events table |",
        "| 2009-03-09 | SPY crisis low | TBD — read CB events table |",
        "| 20XX-XX-XX | Recovery to pre-crisis peak | TBD |",
        "",
        "## Caveats and known biases",
        "",
        "- **yfinance survivor bias on Strategy B is amplified in this window.** ",
        "  Even with the time-aware listing filter and anchor-based alignment, the",
        "  20-name basket is the *2026 winners* set. Names that *would have been in a",
        "  2008-era large-cap basket but later collapsed* (e.g. Citigroup, AIG, Lehman)",
        "  are absent. See `2026-05-12-survivor-bias-stress-test.md` plan for the fix.",
        "- **Cash proxy substitution:** BIL has slightly different yield characteristics ",
        "  than SHV; expect a few bps difference in Strategy A cash-floor returns.",
        "- **First real signals:** ~12 months after the start date (252-day momentum warmup),",
        "  so effective trading window is approximately 2008-06 onward.",
        "",
        "## Decision criteria for the 15% DD ceiling",
        "",
        f"The 2008-inclusive max drawdown is **{mdd}%**.",
        "",
        f"- If {mdd}% <= 15% -> the production DD ceiling holds under crisis stress. ",
        "  Update plan.md to remove/replace the '2008 untested' caveat.",
        f"- If {mdd}% > 15% AND <= 20% -> caveat is real but bounded. Recommend keeping",
        "  the 15% number as a halt-and-review trigger rather than a hard cap.",
        f"- If {mdd}% > 20% -> the production strategy mix cannot meet the 15% DD goal ",
        "  through a 2008-class event. Strategy review required before live.",
    ]

    # Append the actual verdict.
    try:
        mdd_float = float(mdd)
        if mdd_float <= 15.0:
            lines.append("")
            lines.append(f"**VERDICT: PASS — {mdd}% ≤ 15% ceiling holds under 2008-class stress.**")
        elif mdd_float <= 20.0:
            lines.append("")
            lines.append(f"**VERDICT: BORDERLINE — {mdd}% > 15% but ≤ 20%. Caveat is real.**")
        else:
            lines.append("")
            lines.append(f"**VERDICT: FAIL — {mdd}% > 20%. Strategy review required before live.**")
    except ValueError:
        pass

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[2008-bt] wrote {out.relative_to(REPO_ROOT)}")
    print(f"[2008-bt] headline: CAGR={cagr}% MaxDD={mdd}% Sharpe={sharpe} CB-events={n_events}")

    return 0 if result.get("overall") else 1


if __name__ == "__main__":
    sys.exit(main())
