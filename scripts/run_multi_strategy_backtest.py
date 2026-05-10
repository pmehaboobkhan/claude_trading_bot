"""Multi-strategy portfolio backtest.

Runs the three v1 strategies independently with their capital allocations,
then combines daily equity curves into a portfolio-level view. Evaluates
against the **absolute return target** (8-10% annualized, max DD ≤ 15%),
not against SPY.

Uses yfinance for historical data so we can test long windows (2005+).
yfinance is for offline backtest only — production routines use Alpaca.

Usage:
    python scripts/run_multi_strategy_backtest.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Default window: 2005-01-01 → today (full multi-regime test).
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CACHE_DIR = REPO_ROOT / "backtests" / "_yfinance_cache"

from lib import backtest, config, signals  # noqa: E402
from lib.fills import FillModel, simulated_fill_price  # noqa: E402


DEFAULT_ALLOCATION = {
    "dual_momentum_taa": 0.60,
    "large_cap_momentum_top5": 0.30,
    "gold_permanent_overlay": 0.10,
}

TARGET_ANNUAL_RETURN_LOW = 8.0   # %
TARGET_ANNUAL_RETURN_HIGH = 10.0
MAX_DRAWDOWN_CAP = 15.0
MIN_SHARPE = 0.8


def fetch_bars_yfinance(symbol: str) -> list[dict]:
    """Pull full yfinance history with disk cache. Idempotent."""
    import yfinance as yf
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{symbol}.csv"
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
        if rows:
            return rows
    df = yf.download(symbol, start="1995-01-01", end="2026-05-10",
                     progress=False, auto_adjust=True)
    if df.empty:
        return []
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
    with cache_file.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for b in bars:
            w.writerow(b)
    return bars


def align_bars(bars_by_symbol: dict[str, list[dict]], *, start_date: str, end_date: str) -> dict:
    """Intersect dates across symbols and trim to the requested window."""
    if not bars_by_symbol:
        return bars_by_symbol
    # First filter each symbol to the window.
    in_window = {
        sym: [b for b in bars if start_date <= b["ts"][:10] <= end_date]
        for sym, bars in bars_by_symbol.items()
    }
    dates_per_sym = {sym: {b["ts"][:10] for b in bars} for sym, bars in in_window.items()
                     if bars}
    if not dates_per_sym:
        return {}
    common = set.intersection(*dates_per_sym.values())
    return {sym: [b for b in bars if b["ts"][:10] in common]
            for sym, bars in in_window.items() if bars}


# ---------------------------------------------------------------------------
# Strategy C runner: permanent GLD allocation (simple buy & hold)
# ---------------------------------------------------------------------------

def run_strategy_c_gld_permanent(bars: dict, *, start_date: str, end_date: str,
                                 capital: float) -> dict:
    gld_bars = bars["GLD"]
    in_window = [b for b in gld_bars if start_date <= b["ts"][:10] <= end_date]
    if not in_window:
        return {"name": "gold_permanent_overlay", "equity_curve": [], "trades": []}
    fm = FillModel()
    entry_quote = float(in_window[0]["close"])
    entry_price = simulated_fill_price(side="BUY", quote_price=entry_quote, model=fm)
    qty = math.floor(capital / entry_price)
    cash = capital - qty * entry_price
    equity_curve = []
    for b in in_window:
        price = float(b["close"])
        equity_curve.append((b["ts"][:10], cash + qty * price))
    # Realize at end for reporting.
    exit_quote = float(in_window[-1]["close"])
    exit_price = simulated_fill_price(side="CLOSE", quote_price=exit_quote, model=fm)
    final_cash = cash + qty * exit_price
    return {
        "name": "gold_permanent_overlay",
        "equity_curve": equity_curve,
        "trades": [
            {"date": in_window[0]["ts"][:10], "symbol": "GLD", "side": "ENTRY",
             "quantity": qty, "price": entry_price, "pnl": 0.0,
             "rationale": "permanent 10% allocation"},
            {"date": in_window[-1]["ts"][:10], "symbol": "GLD", "side": "EXIT",
             "quantity": qty, "price": exit_price, "pnl": (exit_price - entry_price) * qty,
             "rationale": "end-of-backtest forced close"},
        ],
        "final_equity": final_cash,
        "initial_capital": capital,
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _annualized_return(equity_curve: list[tuple[str, float]],
                       initial_capital: float, trading_days_per_year: int = 252) -> float:
    if not equity_curve or initial_capital <= 0:
        return 0.0
    total_return = equity_curve[-1][1] / initial_capital - 1
    years = len(equity_curve) / trading_days_per_year
    if years <= 0:
        return 0.0
    return ((1 + total_return) ** (1 / years) - 1) * 100


def _max_drawdown_pct(equity_curve: list[tuple[str, float]]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0][1]
    mdd = 0.0
    for _, v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd * 100


def _sharpe(equity_curve: list[tuple[str, float]],
            trading_days_per_year: int = 252) -> float:
    if len(equity_curve) < 2:
        return 0.0
    rets = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1][1]
        cur = equity_curve[i][1]
        if prev > 0:
            rets.append(cur / prev - 1)
    if not rets:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(trading_days_per_year)


def _combine_equity_curves(curves: list[list[tuple[str, float]]]) -> list[tuple[str, float]]:
    """Sum equity curves across strategies day-by-day (assumes aligned dates)."""
    if not curves:
        return []
    # Build a date -> total map.
    by_date: dict[str, float] = {}
    for curve in curves:
        for date, value in curve:
            by_date[date] = by_date.get(date, 0.0) + value
    return sorted(by_date.items())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2005-01-01")
    parser.add_argument("--end", default="2026-05-08")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--alloc-a", type=float, default=DEFAULT_ALLOCATION["dual_momentum_taa"],
                        help="Allocation for dual_momentum_taa (0-1)")
    parser.add_argument("--alloc-b", type=float, default=DEFAULT_ALLOCATION["large_cap_momentum_top5"],
                        help="Allocation for large_cap_momentum_top5 (0-1)")
    parser.add_argument("--alloc-c", type=float, default=DEFAULT_ALLOCATION["gold_permanent_overlay"],
                        help="Allocation for gold_permanent_overlay (0-1)")
    parser.add_argument("--label", default="",
                        help="Optional tag included in the report filename")
    args = parser.parse_args()

    ALLOCATION = {
        "dual_momentum_taa": args.alloc_a,
        "large_cap_momentum_top5": args.alloc_b,
        "gold_permanent_overlay": args.alloc_c,
    }
    total_alloc = sum(ALLOCATION.values())
    if abs(total_alloc - 1.0) > 0.001:
        print(f"FATAL: allocations sum to {total_alloc:.3f}, must equal 1.0")
        return 1

    print(f"Multi-strategy backtest")
    print(f"  Window: {args.start} → {args.end}")
    print(f"  Capital: ${args.capital:,.0f}")
    print(f"  Allocations: A={ALLOCATION['dual_momentum_taa']:.0%} "
          f"B={ALLOCATION['large_cap_momentum_top5']:.0%} "
          f"C={ALLOCATION['gold_permanent_overlay']:.0%}")
    if args.label:
        print(f"  Label: {args.label}")
    print()

    watchlist = config.watchlist()
    symbols = [s["symbol"] for s in watchlist["symbols"]]

    # Need TLT and SHV in addition to watchlist (already there). Pull all symbols.
    print(f"[fetch] pulling {len(symbols)} symbols from yfinance...")
    bars: dict[str, list[dict]] = {}
    for sym in symbols:
        try:
            bars[sym] = fetch_bars_yfinance(sym)
        except Exception as exc:
            print(f"  {sym}: FAILED {exc}")
            continue
        time.sleep(0.05)

    # Align all symbols to the window.
    aligned = align_bars(bars, start_date=args.start, end_date=args.end)
    if "SPY" not in aligned:
        print("FATAL: no SPY in aligned data")
        return 1
    sample_len = len(next(iter(aligned.values())))
    sample_first = next(iter(aligned.values()))[0]["ts"][:10]
    sample_last = next(iter(aligned.values()))[-1]["ts"][:10]
    universe_size = len(aligned)
    print(f"[fetch] aligned to {sample_len} common days ({sample_first} → {sample_last}); "
          f"{universe_size} symbols pass alignment")

    # Some large-cap stocks may IPO mid-window. They drop out of alignment, which biases the
    # large-cap-momentum universe toward survivors with the longest history. For 2005+ we
    # may lose META (IPO 2012), V (IPO 2008), TSLA (IPO 2010), MA (IPO 2006).
    if universe_size < 8:
        print(f"[fetch] WARNING: only {universe_size} symbols in aligned window — "
              f"large-cap momentum may have a thin universe")

    rules = config.strategy_rules()
    # Force all three strategies to ACTIVE for backtest purposes.
    for s in rules.get("allowed_strategies", []):
        if s["name"] in ALLOCATION:
            s["status"] = "ACTIVE_PAPER_TEST"
        else:
            s["status"] = "PAUSED"

    # Determine backtest window (need 252 days of warmup for 12-month momentum).
    warmup = 252
    if sample_len <= warmup:
        print(f"FATAL: only {sample_len} days, need > {warmup} for warmup")
        return 1
    start_date = next(iter(aligned.values()))[warmup]["ts"][:10]
    end_date = sample_last

    # --- Strategy A: dual_momentum_taa ---
    cap_a = args.capital * ALLOCATION["dual_momentum_taa"]
    print(f"\n[strategy A] dual_momentum_taa ${cap_a:,.0f}...")
    t0 = time.time()
    result_a = backtest.run_backtest(
        strategy="dual_momentum_taa",
        bars_by_symbol=aligned,
        watchlist_symbols=symbols,
        strategy_rules=rules,
        start_date=start_date,
        end_date=end_date,
        initial_capital=cap_a,
        max_position_size_pct=100.0,  # TAA holds 1 asset at a time
    )
    print(f"  done in {time.time() - t0:.1f}s; "
          f"return {result_a.total_return_pct:+.2f}%, trades {len(result_a.trades)}")

    # --- Strategy B: large_cap_momentum_top5 ---
    cap_b = args.capital * ALLOCATION["large_cap_momentum_top5"]
    print(f"\n[strategy B] large_cap_momentum_top5 ${cap_b:,.0f}...")
    t0 = time.time()
    result_b = backtest.run_backtest(
        strategy="large_cap_momentum_top5",
        bars_by_symbol=aligned,
        watchlist_symbols=symbols,
        strategy_rules=rules,
        start_date=start_date,
        end_date=end_date,
        initial_capital=cap_b,
        max_position_size_pct=20.0,  # 5 positions = 20% each of strategy B capital
    )
    print(f"  done in {time.time() - t0:.1f}s; "
          f"return {result_b.total_return_pct:+.2f}%, trades {len(result_b.trades)}")

    # --- Strategy C: gold_permanent_overlay ---
    cap_c = args.capital * ALLOCATION["gold_permanent_overlay"]
    print(f"\n[strategy C] gold_permanent_overlay ${cap_c:,.0f}...")
    result_c = run_strategy_c_gld_permanent(
        aligned, start_date=start_date, end_date=end_date, capital=cap_c,
    )
    final_c = result_c["final_equity"]
    return_c = (final_c / cap_c - 1) * 100
    print(f"  return {return_c:+.2f}%")

    # --- Portfolio combine ---
    portfolio_curve = _combine_equity_curves([
        result_a.equity_curve,
        result_b.equity_curve,
        result_c["equity_curve"],
    ])
    if not portfolio_curve:
        print("FATAL: empty portfolio curve")
        return 1

    final_equity = portfolio_curve[-1][1]
    total_return = (final_equity / args.capital - 1) * 100
    ann_return = _annualized_return(portfolio_curve, args.capital)
    mdd = _max_drawdown_pct(portfolio_curve)
    sharpe = _sharpe(portfolio_curve)
    years = len(portfolio_curve) / 252

    # SPY benchmark for context.
    spy_window = [b for b in aligned["SPY"] if start_date <= b["ts"][:10] <= end_date]
    spy_curve = []
    if spy_window:
        spy_start = float(spy_window[0]["close"])
        for b in spy_window:
            spy_curve.append((b["ts"][:10], args.capital * float(b["close"]) / spy_start))
    spy_return = (spy_curve[-1][1] / args.capital - 1) * 100 if spy_curve else 0.0
    spy_ann = _annualized_return(spy_curve, args.capital) if spy_curve else 0.0
    spy_mdd = _max_drawdown_pct(spy_curve) if spy_curve else 0.0
    spy_sharpe = _sharpe(spy_curve) if spy_curve else 0.0

    # --- Print summary ---
    print("\n" + "=" * 78)
    print("PORTFOLIO RESULT")
    print("=" * 78)
    print(f"  Window:              {start_date} → {end_date}  ({years:.1f} years)")
    print(f"  Initial capital:     ${args.capital:,.2f}")
    print(f"  Final equity:        ${final_equity:,.2f}")
    print(f"  Total return:        {total_return:+.2f}%")
    print(f"  Annualized return:   {ann_return:+.2f}%")
    print(f"  Max drawdown:        {mdd:.2f}%")
    print(f"  Sharpe (rough):      {sharpe:.2f}")
    print()
    print(f"  Per-strategy contributions to final equity:")
    print(f"    A (TAA, 60%):       ${result_a.final_equity:>12,.2f}  "
          f"(return {result_a.total_return_pct:+.2f}%)")
    print(f"    B (large-cap mom):  ${result_b.final_equity:>12,.2f}  "
          f"(return {result_b.total_return_pct:+.2f}%)")
    print(f"    C (gold overlay):   ${final_c:>12,.2f}  "
          f"(return {return_c:+.2f}%)")
    print()
    print(f"  SPY buy & hold (context):")
    print(f"    Total return:       {spy_return:+.2f}%")
    print(f"    Annualized:         {spy_ann:+.2f}%")
    print(f"    Max drawdown:       {spy_mdd:.2f}%")
    print(f"    Sharpe:             {spy_sharpe:.2f}")
    print()

    # --- Target checks ---
    print("ABSOLUTE TARGET EVALUATION")
    print("-" * 78)
    hit_low = ann_return >= TARGET_ANNUAL_RETURN_LOW
    hit_high = ann_return >= TARGET_ANNUAL_RETURN_HIGH
    dd_ok = mdd <= MAX_DRAWDOWN_CAP
    sharpe_ok = sharpe >= MIN_SHARPE
    print(f"  Annualized return ≥ {TARGET_ANNUAL_RETURN_LOW}% (low target):    "
          f"{'PASS' if hit_low else 'FAIL'} ({ann_return:.2f}%)")
    print(f"  Annualized return ≥ {TARGET_ANNUAL_RETURN_HIGH}% (high target):   "
          f"{'PASS' if hit_high else 'FAIL'} ({ann_return:.2f}%)")
    print(f"  Max drawdown ≤ {MAX_DRAWDOWN_CAP}%:                {'PASS' if dd_ok else 'FAIL'} "
          f"({mdd:.2f}%)")
    print(f"  Sharpe ≥ {MIN_SHARPE}:                            "
          f"{'PASS' if sharpe_ok else 'FAIL'} ({sharpe:.2f})")
    print()
    overall = hit_low and dd_ok and sharpe_ok
    print(f"  OVERALL: {'PASS — portfolio meets minimum targets' if overall else 'FAIL — see above'}")
    print()
    print(f"  Promotion path: keep all 3 strategies as NEEDS_MORE_DATA until the same "
          f"targets are hit in paper trading for 90+ days AND 30+ closed trades.")

    # --- Write report ---
    report_dir = REPO_ROOT / "backtests" / "multi_strategy_portfolio"
    report_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.label}" if args.label else ""
    report_file = report_dir / f"{start_date}_to_{end_date}{suffix}.md"
    lines = [
        f"# Multi-strategy backtest — {start_date} → {end_date}",
        "",
        "## Portfolio result",
        f"- Initial capital: ${args.capital:,.2f}",
        f"- Final equity: ${final_equity:,.2f}",
        f"- Total return: {total_return:+.2f}%",
        f"- **Annualized return: {ann_return:+.2f}%**",
        f"- **Max drawdown: {mdd:.2f}%**",
        f"- **Sharpe (rough): {sharpe:.2f}**",
        f"- Years: {years:.2f}",
        "",
        "## Allocations and per-strategy contribution",
        "| Strategy | Allocation | Return | Final equity | Trades |",
        "|---|---:|---:|---:|---:|",
        f"| dual_momentum_taa | {ALLOCATION['dual_momentum_taa']:.0%} | "
        f"{result_a.total_return_pct:+.2f}% | ${result_a.final_equity:,.2f} | "
        f"{sum(1 for t in result_a.trades if t['side'] == 'EXIT')} |",
        f"| large_cap_momentum_top5 | {ALLOCATION['large_cap_momentum_top5']:.0%} | "
        f"{result_b.total_return_pct:+.2f}% | ${result_b.final_equity:,.2f} | "
        f"{sum(1 for t in result_b.trades if t['side'] == 'EXIT')} |",
        f"| gold_permanent_overlay | {ALLOCATION['gold_permanent_overlay']:.0%} | "
        f"{return_c:+.2f}% | ${final_c:,.2f} | "
        f"{sum(1 for t in result_c['trades'] if t['side'] == 'EXIT')} |",
        "",
        "## SPY buy & hold (context only — not a hurdle)",
        f"- Total return: {spy_return:+.2f}%",
        f"- Annualized: {spy_ann:+.2f}%",
        f"- Max drawdown: {spy_mdd:.2f}%",
        f"- Sharpe: {spy_sharpe:.2f}",
        "",
        "## Absolute target evaluation",
        f"| Criterion | Result | Actual |",
        f"|---|---|---:|",
        f"| Annualized return ≥ {TARGET_ANNUAL_RETURN_LOW}% (low target) | "
        f"{'PASS' if hit_low else 'FAIL'} | {ann_return:.2f}% |",
        f"| Annualized return ≥ {TARGET_ANNUAL_RETURN_HIGH}% (high target) | "
        f"{'PASS' if hit_high else 'FAIL'} | {ann_return:.2f}% |",
        f"| Max drawdown ≤ {MAX_DRAWDOWN_CAP}% | {'PASS' if dd_ok else 'FAIL'} | {mdd:.2f}% |",
        f"| Sharpe ≥ {MIN_SHARPE} | {'PASS' if sharpe_ok else 'FAIL'} | {sharpe:.2f} |",
        "",
        f"**Overall: {'PASS' if overall else 'FAIL'}**",
        "",
        "## Caveats",
        "- Backtest uses yfinance survivor-biased current S&P 100 large-cap universe;",
        "  large_cap_momentum_top5 results are optimistic for periods where losers were excluded.",
        "- Includes ~4 bps round-trip friction (1bp slippage + 1bp half-spread per side).",
        "- No tax modeling — real-world returns would be lower for short-term gains.",
        "- 12-month momentum warmup means actual trading window is "
        f"{warmup} days shorter than the calendar window.",
    ]
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Report: {report_file.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
