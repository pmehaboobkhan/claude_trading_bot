# scripts/run_cb_threshold_stability.py
"""Stability sweep over circuit-breaker thresholds.

Holds the strategies fixed (60/30/10 with IEF) and sweeps the four CB
thresholds across a small grid centered on the chosen production values
(half_dd=0.08, out_dd=0.12, half->full=0.05, out->half=0.08).

Output: reports/learning/cb_threshold_stability_<date>.md with a table
of (variant, CAGR, MaxDD, Sharpe, n_events) — one row per grid point.

Pass criterion (qualitative, no auto-pass/fail):
- Within +/-1pp of each chosen threshold, CAGR should stay within +/-1.5pp
  and MaxDD within +/-2pp. If those bands are blown, the production point
  is on a peak, not a plateau, and the choice should be reviewed.

Usage:
    python scripts/run_cb_threshold_stability.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_multi_strategy_backtest as mod  # noqa: E402


# Grid: 3 values per axis, centered on the production choices (+/- 1pp).
# Tighter than a wider sweep but covers the plateau-check band exactly.
# Total = 3^4 = 81, constrained to invariants typically yields ~30-40 valid combos.
# (0 < half_dd < out_dd; recovery_dd < half_dd; out_recover_dd < out_dd).
HALF_DD_GRID    = [0.07, 0.08, 0.09]
OUT_DD_GRID     = [0.11, 0.12, 0.13]
HALF_TO_FULL    = [0.04, 0.05, 0.06]
OUT_TO_HALF     = [0.07, 0.08, 0.09]


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
        sma_months=10,
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
    print(f"[stability] {len(combos)} valid combinations over {args.start} -> {args.end}")

    rows = []
    for i, (h, o, htf, oth) in enumerate(combos, 1):
        print(f"  [{i}/{len(combos)}] half={h:.2f} out={o:.2f} "
              f"h->f={htf:.2f} o->h={oth:.2f}")
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
        f"cb_threshold_stability_{datetime.now(UTC):%Y-%m-%d}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Circuit-Breaker Threshold Stability Sweep — {datetime.now(UTC):%Y-%m-%d}",
        "",
        f"Window: {args.start} -> {args.end}",
        f"Strategies: 60/30/10 (TAA / large-cap / gold), IEF as Strategy A bond.",
        f"Total combinations evaluated: {len(rows)}",
        f"Production choice: half_dd=0.08, out_dd=0.12, h->f=0.05, o->h=0.08 (marked **PROD**).",
        "",
        "## All variants (sorted by Sharpe descending)",
        "",
        "| half_dd | out_dd | h->f | o->h | CAGR % | MaxDD % | Sharpe | events | tag |",
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
    prod_row = next((r for r in rows if (r["half_dd"], r["out_dd"], r["h_to_f"], r["o_to_h"]) == PROD), None)
    if prod_row is not None:
        # Strict neighbors: differ from PROD on EXACTLY ONE axis by EXACTLY ONE grid step.
        # (With a 3-value grid spaced 0.01 apart, that's 8 neighbors max: 2 per axis.)
        def _diffs(r):
            return (
                round(r["half_dd"] - PROD[0], 4),
                round(r["out_dd"] - PROD[1], 4),
                round(r["h_to_f"] - PROD[2], 4),
                round(r["o_to_h"] - PROD[3], 4),
            )

        neighbors = []
        for r in rows:
            if (r["half_dd"], r["out_dd"], r["h_to_f"], r["o_to_h"]) == PROD:
                continue
            diffs = _diffs(r)
            nonzero = [d for d in diffs if d != 0.0]
            if len(nonzero) == 1 and abs(nonzero[0]) <= 0.01 + 1e-9:
                neighbors.append(r)

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
                "## Plateau check (strict neighbors: 1 threshold differs by 1 grid step)",
                "",
                f"- Production CAGR: {prod_row['cagr']:+.2f}% / MaxDD: {prod_row['mdd']:.2f}% / Sharpe: {prod_row['sharpe']:.2f}",
                f"- Strict neighbors: {len(neighbors)} combos (of {len(rows) - 1} non-PROD)",
                f"- Neighbor CAGR range: {cagr_min:+.2f}% to {cagr_max:+.2f}% (band {cagr_band:.2f}pp)",
                f"- Neighbor MaxDD range: {mdd_min:.2f}% to {mdd_max:.2f}% (band {mdd_band:.2f}pp)",
                f"- **Plateau verdict:** {'PASS — within ±1.5pp CAGR and ±2pp MaxDD bands' if plateau else 'FAIL — production choice may be overfit; review thresholds'}",
            ]

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[stability] wrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
