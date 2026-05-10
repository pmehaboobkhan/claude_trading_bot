"""CLI: fetch historical bars from Alpaca, run a backtest, write a report.

Usage:
    python scripts/run_backtest.py [--strategy NAME] [--years N] [--capital N]

Examples:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --strategy sector_relative_strength_rotation --years 5
    python scripts/run_backtest.py --strategy regime_defensive_tilt --years 3 --capital 100000

Reads credentials from env (ALPACA_PAPER_KEY_ID / ALPACA_PAPER_SECRET_KEY).
Source `.env.local` first if you keep keys there:
    set -a; source .env.local; set +a
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


def fetch_bars_for_symbol(symbol: str, *, years: int) -> list[dict]:
    """Pull `years` of daily bars for `symbol` from Alpaca free IEX feed."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    import os
    key_id = os.environ["ALPACA_PAPER_KEY_ID"]
    secret = os.environ["ALPACA_PAPER_SECRET_KEY"]
    client = StockHistoricalDataClient(key_id, secret)

    end = datetime.now(UTC) - timedelta(minutes=20)  # IEX free tier delay
    start = end - timedelta(days=years * 365 + 30)  # buffer for warmup
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )
    resp = client.get_stock_bars(req)
    bars_obj = resp.data.get(symbol, [])
    return [
        {
            "ts": b.timestamp.isoformat(),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": int(b.volume),
        }
        for b in bars_obj
    ]


def align_bars(bars_by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Align all symbols to the intersection of their trading dates (by SPY-canonical timeline).

    Some symbols may have shorter history (e.g., XLC inception in 2018). For the backtest we
    take the latest common start date so every symbol has data over the full window.
    """
    if not bars_by_symbol:
        return bars_by_symbol
    dates_per_sym = {sym: {b["ts"][:10] for b in bars} for sym, bars in bars_by_symbol.items()}
    common = set.intersection(*dates_per_sym.values()) if dates_per_sym else set()
    return {
        sym: [b for b in bars if b["ts"][:10] in common]
        for sym, bars in bars_by_symbol.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="sector_relative_strength_rotation",
                        choices=[
                            "sector_relative_strength_rotation",
                            "regime_defensive_tilt",
                            "trend_pullback_in_leader",
                            "spy_neutral_default",
                        ])
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--capital", type=float, default=100_000.0)
    args = parser.parse_args()

    watchlist = config.watchlist()
    symbols = [s["symbol"] for s in watchlist["symbols"]]
    strategy_rules = config.strategy_rules()

    print(f"[backtest] strategy={args.strategy} years={args.years} capital=${args.capital:,.0f}")
    print(f"[backtest] symbols: {', '.join(symbols)}")

    # Some strategies require their status be active for `evaluate_all` to emit signals.
    # For backtesting, force the target strategy to ACTIVE_PAPER_TEST regardless of its config
    # status (otherwise we couldn't backtest NEEDS_MORE_DATA strategies — which is the point).
    for s in strategy_rules.get("allowed_strategies", []):
        if s["name"] == args.strategy:
            s["status"] = "ACTIVE_PAPER_TEST"
    # Disable other strategies during this run so cross-strategy entries don't pollute results.
    for s in strategy_rules.get("allowed_strategies", []):
        if s["name"] != args.strategy and s["name"] != "spy_neutral_default":
            s["status"] = "PAUSED"

    bars_by_symbol: dict[str, list[dict]] = {}
    for sym in symbols:
        print(f"[backtest] fetching {sym}...", end=" ", flush=True)
        t0 = time.time()
        try:
            bars = fetch_bars_for_symbol(sym, years=args.years)
        except Exception as exc:
            print(f"FAILED: {exc}")
            continue
        print(f"{len(bars)} bars in {time.time() - t0:.1f}s")
        bars_by_symbol[sym] = bars
        time.sleep(0.1)  # be polite to the API

    if "SPY" not in bars_by_symbol:
        print("[backtest] FATAL: no SPY bars; aborting")
        return 1

    aligned = align_bars(bars_by_symbol)
    sample = next(iter(aligned.values()))
    print(f"[backtest] aligned to {len(sample)} common trading days")
    if sample:
        print(f"[backtest] window: {sample[0]['ts'][:10]} → {sample[-1]['ts'][:10]}")

    # Resolve start/end dates from the aligned window.
    start_date = sample[200]["ts"][:10] if len(sample) > 200 else sample[0]["ts"][:10]
    end_date = sample[-1]["ts"][:10]

    print(f"[backtest] running event-driven backtest {start_date} → {end_date}...")
    t0 = time.time()
    result = backtest.run_backtest(
        strategy=args.strategy,
        bars_by_symbol=aligned,
        watchlist_symbols=symbols,
        strategy_rules=strategy_rules,
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.capital,
    )
    print(f"[backtest] done in {time.time() - t0:.1f}s")

    output_dir = REPO_ROOT / "backtests" / args.strategy
    report = backtest.write_report(result, output_dir=output_dir)
    print(f"[backtest] report: {report}")
    print()
    print(f"  Total return:   {result.total_return_pct:+.2f}%")
    print(f"  Final equity:   ${result.final_equity:,.2f}")
    print(f"  Trades closed:  {sum(1 for t in result.trades if t['side'] == 'EXIT')}")
    spy_curve = result.benchmark_curves.get("SPY", [])
    if spy_curve:
        spy_ret = (spy_curve[-1][1] / args.capital - 1) * 100
        print(f"  SPY buy&hold:   {spy_ret:+.2f}%")
        print(f"  Alpha vs SPY:   {result.total_return_pct - spy_ret:+.2f}%")
    ew_curve = result.benchmark_curves.get("SECTOR_EW", [])
    if ew_curve:
        ew_ret = (ew_curve[-1][1] / args.capital - 1) * 100
        print(f"  Sector EW b&h:  {ew_ret:+.2f}%")
        print(f"  Alpha vs EW:    {result.total_return_pct - ew_ret:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
