"""SMA-window stability sweep for Strategy A.

Runs the full multi-strategy backtest 5 times with sma_months in {8,9,10,11,12}
and prints/writes the comparison. Production choice is 10.

Pass criterion: across 8-12 months, CAGR within +/-1.5pp and MaxDD within +/-2pp.

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
        f"Window: {args.start} -> {args.end}",
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
        "## Plateau check (8 <= months <= 12)",
        "",
        f"- CAGR band: {cagr_band:.2f}pp (gate: <= 1.5pp)",
        f"- MaxDD band: {mdd_band:.2f}pp (gate: <= 2.0pp)",
        f"- **Verdict:** {'PASS — broad plateau' if plateau else 'FAIL — SMA choice is on a peak'}",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[sma] wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
