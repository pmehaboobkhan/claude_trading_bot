"""Run the rotation strategy sweep on multiple historical windows using yfinance data.

Used for option D: out-of-regime testing. yfinance has 25+ years of data for most US
equities, which Alpaca's free IEX feed does not provide. yfinance is NOT used for
production trading — only for offline backtest validation.

Universe coverage by inception:
  SPY:                              1993-01
  XLK XLF XLE XLV XLY XLP XLI XLB:  1998-12  (9 sectors)
  XLU:                              1998-12
  XLRE:                             2015-10
  XLC:                              2018-06

Behavior: for each window, automatically uses whatever ETFs have full coverage.

Cache: bars are saved to backtests/_yfinance_cache/<symbol>.csv so repeated runs
are fast. Delete the cache directory to force a fresh pull.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CACHE_DIR = REPO_ROOT / "backtests" / "_yfinance_cache"

from lib import backtest, config  # noqa: E402

# Same variant set as scripts/run_param_sweep.py (consistency across windows).
VARIANTS: list[tuple[str, dict, str]] = [
    ("baseline_20_60_3_5", {"short_window": 20, "long_window": 60, "entry_topn": 3, "exit_topn": 5},
     "20/60d, top-3 entry, top-5 exit"),
    ("concentrated_20_60_2_3", {"short_window": 20, "long_window": 60, "entry_topn": 2, "exit_topn": 3},
     "20/60d, top-2 entry, top-3 exit"),
    ("faster_10_30_3_5", {"short_window": 10, "long_window": 30, "entry_topn": 3, "exit_topn": 5},
     "10/30d, top-3 entry, top-5 exit"),
    ("faster_concentrated_10_30_2_3", {"short_window": 10, "long_window": 30, "entry_topn": 2, "exit_topn": 3},
     "10/30d, top-2 entry, top-3 exit"),
    ("slow_60_120_3_5", {"short_window": 60, "long_window": 120, "entry_topn": 3, "exit_topn": 5},
     "60/120d, top-3 entry, top-5 exit"),
]

# Test windows (informative regimes).
WINDOWS: list[tuple[str, str, str, str]] = [
    ("post_gfc_recovery_2010_2015", "2010-01-01", "2015-12-31",
     "Post-GFC recovery — value-led, pre-mega-cap-tech dominance"),
    ("pre_covid_to_covid_2015_2020", "2015-01-01", "2020-12-31",
     "Pre-Mag-7 era through COVID crash"),
    ("recent_2022_2026", "2022-01-01", "2026-05-08",
     "Recent — Mag-7 era (same window as Alpaca backtest, for cross-check)"),
]


def _cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.csv"


def fetch_bars_yfinance(symbol: str, *, start: str, end: str) -> list[dict]:
    """Fetch daily bars from yfinance, caching all available history per symbol."""
    import yfinance as yf
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(symbol)

    if cache_file.exists():
        rows: list[dict] = []
        with cache_file.open() as f:
            for row in csv.DictReader(f):
                rows.append({
                    "ts": row["ts"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(float(row["volume"])),
                })
        # If cache covers the requested window, use it.
        if rows and rows[0]["ts"][:10] <= start and rows[-1]["ts"][:10] >= end:
            return [r for r in rows if start <= r["ts"][:10] <= end]

    # Otherwise pull full history (1990-01-01 → today).
    df = yf.download(symbol, start="1990-01-01", end="2026-05-09",
                     progress=False, auto_adjust=True)
    if df.empty:
        return []
    # yfinance returns a DataFrame; flatten possible MultiIndex columns.
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    bars: list[dict] = []
    for ts, row in df.iterrows():
        bars.append({
            "ts": ts.strftime("%Y-%m-%dT00:00:00Z"),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    # Cache all of it.
    with cache_file.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for b in bars:
            w.writerow(b)
    return [b for b in bars if start <= b["ts"][:10] <= end]


def align_bars(bars_by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    if not bars_by_symbol:
        return bars_by_symbol
    dates_per_sym = {sym: {b["ts"][:10] for b in bars} for sym, bars in bars_by_symbol.items()}
    common = set.intersection(*dates_per_sym.values())
    return {sym: [b for b in bars if b["ts"][:10] in common] for sym, bars in bars_by_symbol.items()}


def run_one_window(window_name: str, start_date: str, end_date: str,
                   description: str, capital: float) -> dict:
    print(f"\n{'=' * 80}")
    print(f"WINDOW: {window_name}  ({start_date} → {end_date})")
    print(f"  {description}")
    print(f"{'=' * 80}")

    full_universe = ["SPY", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB",
                     "XLRE", "XLU", "XLC"]
    bars: dict[str, list[dict]] = {}
    for sym in full_universe:
        try:
            b = fetch_bars_yfinance(sym, start=start_date, end=end_date)
            if len(b) >= 250:  # need warmup + meaningful test
                bars[sym] = b
                print(f"  {sym}: {len(b)} bars ({b[0]['ts'][:10]} → {b[-1]['ts'][:10]})")
            else:
                print(f"  {sym}: insufficient coverage ({len(b)} bars) — dropping")
        except Exception as exc:
            print(f"  {sym}: FAILED {exc}")
        time.sleep(0.1)

    if "SPY" not in bars:
        print("  FATAL: no SPY data, skipping window")
        return {"window": window_name, "error": "no SPY"}

    aligned = align_bars(bars)
    sample = next(iter(aligned.values()))
    print(f"  aligned to {len(sample)} common days")
    if len(sample) < 230:
        print(f"  warning: only {len(sample)} days — backtest may be unreliable")

    # Need 200-day warmup.
    warmup_start = sample[200]["ts"][:10] if len(sample) > 200 else sample[0]["ts"][:10]
    test_end = sample[-1]["ts"][:10]

    symbols = list(aligned.keys())

    # Precompute benchmarks once per window.
    spy_at_start = next(float(b["close"]) for b in aligned["SPY"]
                        if b["ts"][:10] == warmup_start)
    spy_at_end = float(aligned["SPY"][-1]["close"])
    spy_return = (spy_at_end / spy_at_start - 1) * 100

    sector_syms = [s for s in symbols if s != "SPY"]
    ew_end = 0.0
    for sym in sector_syms:
        sb = aligned[sym]
        s_start = next(float(b["close"]) for b in sb if b["ts"][:10] == warmup_start)
        per_sector = capital / len(sector_syms)
        ew_end += per_sector * (float(sb[-1]["close"]) / s_start)
    ew_return = (ew_end / capital - 1) * 100

    print(f"\n  Benchmarks for {warmup_start} → {test_end}:")
    print(f"    SPY buy & hold:   {spy_return:+.2f}%")
    print(f"    Sector EW b & h:  {ew_return:+.2f}% (universe size: {len(sector_syms)})")

    rules = config.strategy_rules()
    for s in rules.get("allowed_strategies", []):
        if s["name"] == "sector_relative_strength_rotation":
            s["status"] = "ACTIVE_PAPER_TEST"
        elif s["name"] != "spy_neutral_default":
            s["status"] = "PAUSED"

    out: list[dict] = []
    for variant_name, params, _desc in VARIANTS:
        result = backtest.run_backtest(
            strategy="sector_relative_strength_rotation",
            bars_by_symbol=aligned,
            watchlist_symbols=symbols,
            strategy_rules=rules,
            start_date=warmup_start,
            end_date=test_end,
            initial_capital=capital,
            strategy_params={"sector_relative_strength_rotation": params},
        )
        out_dir = REPO_ROOT / "backtests" / "param_sweep_yf" / window_name / variant_name
        backtest.write_report(result, output_dir=out_dir)
        trades = sum(1 for t in result.trades if t["side"] == "EXIT")
        alpha_spy = result.total_return_pct - spy_return
        alpha_ew = result.total_return_pct - ew_return
        out.append({
            "variant": variant_name,
            "return": result.total_return_pct,
            "alpha_spy": alpha_spy,
            "alpha_ew": alpha_ew,
            "trades": trades,
        })

    print(f"\n  {'variant':<32} {'return':>9} {'α vs SPY':>10} {'α vs EW':>10} {'trades':>7}")
    print(f"  {'-' * 80}")
    for r in sorted(out, key=lambda x: x["alpha_spy"], reverse=True):
        print(f"  {r['variant']:<32} {r['return']:>8.2f}% "
              f"{r['alpha_spy']:>+9.2f}% {r['alpha_ew']:>+9.2f}% {r['trades']:>7}")

    any_beat_spy = any(r["alpha_spy"] > 0 for r in out)
    print(f"\n  Any variant beat SPY in this window? {'YES' if any_beat_spy else 'NO'}")

    return {
        "window": window_name,
        "start_date": warmup_start,
        "end_date": test_end,
        "spy_return": spy_return,
        "ew_return": ew_return,
        "universe_size": len(sector_syms),
        "variants": out,
        "any_beat_spy": any_beat_spy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=100_000.0)
    args = parser.parse_args()

    print("Out-of-regime sweep using yfinance data")
    print(f"Capital per window: ${args.capital:,.0f}")
    print(f"Variants per window: {len(VARIANTS)}")
    print(f"Cache dir: {CACHE_DIR.relative_to(REPO_ROOT)}")

    all_results = []
    for window_name, start, end, desc in WINDOWS:
        all_results.append(run_one_window(window_name, start, end, desc, args.capital))

    # Cross-window summary.
    print("\n" + "=" * 80)
    print("CROSS-WINDOW SUMMARY")
    print("=" * 80)
    print(f"{'window':<36} {'SPY':>9} {'EW':>9} {'best α SPY':>12}")
    print("-" * 80)
    for r in all_results:
        if "error" in r:
            print(f"{r['window']:<36}  ERROR: {r['error']}")
            continue
        best_alpha = max(v["alpha_spy"] for v in r["variants"])
        print(f"{r['window']:<36} {r['spy_return']:>+8.2f}% {r['ew_return']:>+8.2f}% "
              f"{best_alpha:>+11.2f}%")

    any_window_beat = any(r.get("any_beat_spy") for r in all_results)
    print()
    print(f"Did ANY variant beat SPY in ANY window? {'YES' if any_window_beat else 'NO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
