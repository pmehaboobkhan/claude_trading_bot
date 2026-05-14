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
import re
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
    body = backtest_report.read_text(encoding="utf-8")

    def grab(pattern: str, default: str = "?") -> str:
        m = re.search(pattern, body)
        return m.group(1) if m else default

    cagr = grab(r"\*\*Annualized return:\s*([+-]?\d+\.\d+)%")
    mdd = grab(r"\*\*Max drawdown:\s*(\d+\.\d+)%")
    sharpe = grab(r"\*\*Sharpe \(rough\):\s*(\d+\.\d+)")
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
        "- The maximum drawdown depth during 2008-09 → 2009-03 specifically",
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
        f"- If {mdd}% <= 15% -> the production DD ceiling holds under crisis stress. ",
        "  Update plan.md to remove the '2008 untested' caveat.",
        f"- If {mdd}% > 15% AND <= 20% -> caveat is real but bounded. Recommend keeping",
        "  the 15% number as a halt-and-review trigger rather than a hard cap, and",
        "  surface this in the next monthly review.",
        f"- If {mdd}% > 20% -> the production strategy mix cannot meet the 15% DD goal ",
        "  through a 2008-class event. Either widen the breaker thresholds (tighter ",
        "  HALF/OUT triggers) or accept a higher DD ceiling in CLAUDE.md.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[2008-bt] wrote {out.relative_to(REPO_ROOT)}")
    print(f"[2008-bt] headline: CAGR={cagr}% MaxDD={mdd}% Sharpe={sharpe} CB-events={n_events}")

    # Print DD verdict for easy scanning
    try:
        mdd_float = float(mdd)
        if mdd_float <= 15.0:
            print(f"[2008-bt] DD VERDICT: PASS — {mdd}% <= 15% ceiling holds under crisis stress")
        elif mdd_float <= 20.0:
            print(f"[2008-bt] DD VERDICT: BORDERLINE — {mdd}% > 15% but <= 20%; caveat is real")
        else:
            print(f"[2008-bt] DD VERDICT: FAIL — {mdd}% > 20%; strategy review required before live")
    except ValueError:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
