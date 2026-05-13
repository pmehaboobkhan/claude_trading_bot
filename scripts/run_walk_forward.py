"""Walk-forward CB threshold evaluation.

For each fold:
  1. On the IS window, sweep a small CB threshold grid and pick the best
     by Sharpe subject to MaxDD <= 15%.
  2. Run that chosen threshold on the OOS window.
  3. Record OOS metrics + the chosen params.

Then chain OOS daily returns across folds and report aggregate
CAGR / MaxDD / Sharpe -- the honest forward-performance estimate.

Usage:
    python scripts/run_walk_forward.py [--full-start YYYY-MM-DD] [--full-end YYYY-MM-DD]
                                       [--is-years 5] [--oos-years 1] [--step-years 1]
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.walk_forward import generate_windows, select_best, aggregate_oos, add_years  # noqa: E402
from scripts import run_multi_strategy_backtest as mod  # noqa: E402

# Engine requires ~252 trading days of warmup before signals fire.
# We pass an extra year of bars before each OOS window so the engine has
# enough history; it then internally trims the equity_curve to OOS dates.
WARMUP_YEARS = 1

# Smaller IS grid than Task 2 -- walk-forward runs this 5-10 times per fold
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
        print(f"\n[wf fold {i}/{len(folds)}] IS {is_s}->{is_e} | OOS {oos_s}->{oos_e}")

        # IS sweep
        is_results = []
        for (h, o, htf, oth) in IS_GRID:
            r = mod.run_backtest(make_args(is_s, is_e, h, o, htf, oth))
            is_results.append({
                "params": {"half_dd": h, "out_dd": o, "h_to_f": htf, "o_to_h": oth},
                "metrics": {"sharpe": r["sharpe"], "cagr": r["ann_return"],
                            "mdd": r["max_drawdown_pct"]},
            })

        try:
            chosen = select_best(is_results, by="sharpe", max_mdd_pct=15.0)
        except ValueError:
            # No candidate met the DD cap -- pick the lowest-DD candidate as a fallback
            print(f"  IS: no candidate met MaxDD<=15%; falling back to lowest-DD")
            chosen = min(is_results, key=lambda c: c["metrics"]["mdd"])
        p = chosen["params"]
        print(f"  IS chose: half={p['half_dd']:.2f} out={p['out_dd']:.2f} "
              f"h->f={p['h_to_f']:.2f} o->h={p['o_to_h']:.2f} "
              f"(IS Sharpe={chosen['metrics']['sharpe']:.2f}, "
              f"IS MDD={chosen['metrics']['mdd']:.2f}%)")

        # OOS run with chosen params.
        # The backtest engine requires > 252 warmup days before signal evaluation.
        # Pass a *fetch* start 1 year before oos_s so the engine consumes pre-OOS
        # data as warmup; the engine internally trims the equity_curve to start
        # after warmup, so the resulting metrics are over [oos_s, oos_e].
        oos_fetch_start = add_years(oos_s, -WARMUP_YEARS)
        oos = mod.run_backtest(make_args(oos_fetch_start, oos_e,
                                         p["half_dd"], p["out_dd"],
                                         p["h_to_f"], p["o_to_h"]))
        # Defense in depth: filter equity_curve to dates >= oos_s explicitly.
        # The engine already trims warmup, but pinning this behavior here protects
        # against future engine changes that might leave warmup-period entries in.
        oos_curve = [(d, v) for d, v in oos["equity_curve"] if d >= oos_s]
        oos_returns = daily_returns_from_curve(oos_curve)
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
        f"walk_forward_cb_{datetime.now(UTC):%Y-%m-%d}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Walk-Forward CB Threshold Evaluation -- {datetime.now(UTC):%Y-%m-%d}",
        "",
        f"Window: {args.full_start} -> {args.full_end}",
        f"Folds: {len(folds)} | IS {args.is_years}y | OOS {args.oos_years}y | "
        f"Step {args.step_years}y",
        f"IS grid: {len(IS_GRID)} candidate threshold sets per fold",
        f"Selection rule: max IS Sharpe subject to IS MaxDD <= 15%",
        "",
        "## Per-fold results",
        "",
        "| Fold | IS window | OOS window | Chosen (h/o/h->f/o->h) | IS Sharpe | OOS CAGR % | OOS MDD % | OOS Sharpe |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for i, rec in enumerate(fold_records, 1):
        p = rec["chosen_params"]
        lines.append(
            f"| {i} | {rec['is_start']}->{rec['is_end']} | "
            f"{rec['oos_start']}->{rec['oos_end']} | "
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
        "Full-window IS (production thresholds 0.08/0.12/0.05/0.08, 2013-05-24 -> 2026-05-08):",
        "- CAGR: +11.15% | MaxDD: 12.68% | Sharpe: 1.14 (per `pivot_validation_2026-05-10.md`)",
        "",
        f"OOS-chained: CAGR {agg['chained_cagr']:+.2f}% | MaxDD {agg['chained_mdd']:.2f}% | "
        f"Sharpe {agg['chained_sharpe']:.2f}",
        "",
        "**Interpretation guide:**",
        "- If OOS CAGR > IS - 2pp AND OOS MDD < IS + 3pp -> no overfitting evidence.",
        "- If OOS CAGR < IS - 4pp OR OOS MDD > IS + 5pp -> overfitting concern; review.",
        "- If chosen params differ substantially across folds -> CB choice is regime-dependent;",
        "  document and consider regime-conditional thresholds (deferred to future work).",
        "",
        "## Caveats",
        f"- {args.is_years}-year IS window means first usable OOS year is "
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
