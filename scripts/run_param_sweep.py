"""Run a parameter sweep on sector_relative_strength_rotation.

Tests a small set of variants against the same historical window. Honest about
in-sample overfitting risk — the sweep itself doesn't prove anything; out-of-sample
validation is required before any variant is promoted.

Usage:
    python scripts/run_param_sweep.py [--years N] [--capital N]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import backtest, config  # noqa: E402

# (variant_name, params, description)
VARIANTS: list[tuple[str, dict, str]] = [
    ("baseline_20_60_3_5", {"short_window": 20, "long_window": 60, "entry_topn": 3, "exit_topn": 5},
     "Current production: 20/60d windows, top-3 entry, top-5 exit"),
    ("concentrated_20_60_2_3", {"short_window": 20, "long_window": 60, "entry_topn": 2, "exit_topn": 3},
     "More concentrated: top-2 entry, top-3 exit"),
    ("faster_10_30_3_5", {"short_window": 10, "long_window": 30, "entry_topn": 3, "exit_topn": 5},
     "Faster windows: 10/30d (more responsive, more noise)"),
    ("faster_concentrated_10_30_2_3", {"short_window": 10, "long_window": 30, "entry_topn": 2, "exit_topn": 3},
     "Faster + concentrated combo"),
    ("slow_60_120_3_5", {"short_window": 60, "long_window": 120, "entry_topn": 3, "exit_topn": 5},
     "Slow windows: 60/120d (smoother, fewer trades)"),
]


def fetch_bars_for_symbol(symbol: str, *, years: int) -> list[dict]:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    import os
    client = StockHistoricalDataClient(os.environ["ALPACA_PAPER_KEY_ID"], os.environ["ALPACA_PAPER_SECRET_KEY"])
    end = datetime.now(UTC) - timedelta(minutes=20)
    start = end - timedelta(days=years * 365 + 30)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start, end=end)
    resp = client.get_stock_bars(req)
    return [
        {"ts": b.timestamp.isoformat(), "open": float(b.open), "high": float(b.high),
         "low": float(b.low), "close": float(b.close), "volume": int(b.volume)}
        for b in resp.data.get(symbol, [])
    ]


def align_bars(bars_by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    if not bars_by_symbol:
        return bars_by_symbol
    dates_per_sym = {sym: {b["ts"][:10] for b in bars} for sym, bars in bars_by_symbol.items()}
    common = set.intersection(*dates_per_sym.values())
    return {sym: [b for b in bars if b["ts"][:10] in common] for sym, bars in bars_by_symbol.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--capital", type=float, default=100_000.0)
    args = parser.parse_args()

    watchlist = config.watchlist()
    symbols = [s["symbol"] for s in watchlist["symbols"]]
    rules = config.strategy_rules()
    for s in rules.get("allowed_strategies", []):
        if s["name"] == "sector_relative_strength_rotation":
            s["status"] = "ACTIVE_PAPER_TEST"
        elif s["name"] != "spy_neutral_default":
            s["status"] = "PAUSED"

    print(f"[sweep] fetching {len(symbols)} symbols, {args.years}y of bars...")
    bars: dict[str, list[dict]] = {}
    for sym in symbols:
        try:
            bars[sym] = fetch_bars_for_symbol(sym, years=args.years)
        except Exception as exc:
            print(f"[sweep] {sym}: FAILED {exc}")
    if "SPY" not in bars:
        print("[sweep] FATAL: no SPY")
        return 1
    aligned = align_bars(bars)
    sample = next(iter(aligned.values()))
    print(f"[sweep] aligned to {len(sample)} common days "
          f"({sample[0]['ts'][:10]} → {sample[-1]['ts'][:10]})")

    start_date = sample[200]["ts"][:10] if len(sample) > 200 else sample[0]["ts"][:10]
    end_date = sample[-1]["ts"][:10]
    print(f"[sweep] backtest window: {start_date} → {end_date}\n")

    # Pre-compute benchmark returns once (same for every variant).
    spy_bars = aligned["SPY"]
    spy_at_start = next(float(b["close"]) for b in spy_bars if b["ts"][:10] == start_date)
    spy_at_end = float(spy_bars[-1]["close"])
    spy_return_pct = (spy_at_end / spy_at_start - 1) * 100

    sector_syms = [s for s in symbols if s != "SPY"]
    ew_start_value = 0.0
    ew_end_value = 0.0
    for sym in sector_syms:
        sb = aligned.get(sym, [])
        s_start = next((float(b["close"]) for b in sb if b["ts"][:10] == start_date), None)
        if s_start:
            per_sector = args.capital / len(sector_syms)
            ew_start_value += per_sector
            ew_end_value += per_sector * (float(sb[-1]["close"]) / s_start)
    ew_return_pct = (ew_end_value / args.capital - 1) * 100 if args.capital else 0

    print(f"[sweep] benchmarks for this window:")
    print(f"  SPY buy & hold:   {spy_return_pct:+.2f}%")
    print(f"  Sector EW b & h:  {ew_return_pct:+.2f}%\n")

    results: list[tuple[str, str, "object", dict]] = []
    for variant_name, params, desc in VARIANTS:
        print(f"[sweep] {variant_name}: {desc}")
        t0 = time.time()
        result = backtest.run_backtest(
            strategy="sector_relative_strength_rotation",
            bars_by_symbol=aligned,
            watchlist_symbols=symbols,
            strategy_rules=rules,
            start_date=start_date,
            end_date=end_date,
            initial_capital=args.capital,
            strategy_params={"sector_relative_strength_rotation": params},
        )
        elapsed = time.time() - t0
        report = backtest.write_report(
            result,
            output_dir=REPO_ROOT / "backtests" / "param_sweep" / variant_name,
        )
        trades = sum(1 for t in result.trades if t["side"] == "EXIT")
        alpha_spy = result.total_return_pct - spy_return_pct
        alpha_ew = result.total_return_pct - ew_return_pct
        print(f"  return={result.total_return_pct:+.2f}% | "
              f"trades={trades} | α vs SPY={alpha_spy:+.2f} | α vs EW={alpha_ew:+.2f} | "
              f"({elapsed:.1f}s)")
        print(f"  report: {report.relative_to(REPO_ROOT)}\n")
        results.append((variant_name, desc, result, params))

    print("=" * 80)
    print("SWEEP SUMMARY (sorted by alpha vs SPY)")
    print("=" * 80)
    print(f"{'variant':<32} {'return':>9} {'α vs SPY':>10} {'α vs EW':>10} {'trades':>7}")
    print("-" * 80)
    sorted_results = sorted(results,
                            key=lambda r: r[2].total_return_pct - spy_return_pct,
                            reverse=True)
    for variant_name, _desc, result, _params in sorted_results:
        trades = sum(1 for t in result.trades if t["side"] == "EXIT")
        alpha_spy = result.total_return_pct - spy_return_pct
        alpha_ew = result.total_return_pct - ew_return_pct
        print(f"{variant_name:<32} {result.total_return_pct:>8.2f}% "
              f"{alpha_spy:>+9.2f}% {alpha_ew:>+9.2f}% {trades:>7}")
    print()
    print(f"SPY benchmark: {spy_return_pct:+.2f}%")
    print(f"EW benchmark:  {ew_return_pct:+.2f}%")
    print()
    any_beat_spy = any(r[2].total_return_pct > spy_return_pct for r in results)
    print(f"Any variant beat SPY? {'YES' if any_beat_spy else 'NO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
