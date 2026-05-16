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

from lib import backtest, config, portfolio_risk, signals  # noqa: E402
from lib.backtest import BacktestResult, Position  # noqa: E402
from lib.fills import FillModel, simulated_fill_price  # noqa: E402
from lib.historical_universe import filter_bars_by_listing  # noqa: E402
from lib import historical_membership  # noqa: E402


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
# Cash bucket: SHV buy-and-hold (no rebalancing back to target weight)
# ---------------------------------------------------------------------------

def run_cash_bucket_shv(bars: dict, *, start_date: str, end_date: str,
                       capital: float, cash_proxy: str = "SHV") -> dict:
    """Hold the cash proxy from start_date to end_date. No friction (cash; we never trade it).

    Args:
        cash_proxy: The ETF symbol to use as the cash equivalent (SHV, BIL, or SHY).
                    Default SHV. BIL/SHY are used for long-window backtests starting
                    before SHV's 2007 listing date.
    """
    proxy_bars = bars[cash_proxy]
    in_window = [b for b in proxy_bars if start_date <= b["ts"][:10] <= end_date]
    if not in_window:
        return {"equity_curve": [], "final_equity": capital}
    start_price = float(in_window[0]["close"])
    qty = capital / start_price  # fractional shares OK for cash modeling
    curve = [(b["ts"][:10], qty * float(b["close"])) for b in in_window]
    return {"equity_curve": curve, "final_equity": curve[-1][1]}


# ---------------------------------------------------------------------------
# Circuit-breaker: portfolio-level drawdown throttle
# ---------------------------------------------------------------------------
# State-machine logic lives in lib/portfolio_risk so paper trading and the
# backtest share a single source of truth. This function just orchestrates the
# daily walk over precomputed equity curves.


def _daily_returns(curve: list[tuple[str, float]]) -> list[tuple[str, float]]:
    if len(curve) < 2:
        return [(d, 0.0) for d, _ in curve]
    out = [(curve[0][0], 0.0)]
    for i in range(1, len(curve)):
        prev = curve[i - 1][1]
        cur = curve[i][1]
        out.append((curve[i][0], (cur / prev) - 1 if prev > 0 else 0.0))
    return out


def apply_circuit_breaker(
    strategy_combined_curve: list[tuple[str, float]],
    shv_curve: list[tuple[str, float]],
    initial_capital: float,
    *,
    half_dd: float,
    out_dd: float,
    recovery_dd: float,
    out_recover_dd: float,
    per_strategy_curves: dict[str, list[tuple[str, float]]] | None = None,
    target_weights: dict[str, float] | None = None,
) -> tuple[list[tuple[str, float]], list[dict]]:
    """Walk daily with a portfolio DD throttle.

    Returns (portfolio_equity_curve, throttle_events).
    `strategy_combined_curve` is the sum of all strategy equity curves over time.
    `shv_curve` is an SHV buy-and-hold curve on $1 of capital, used to compute
    the cash leg's daily return.

    If `per_strategy_curves` and `target_weights` are provided (the corrected
    path, 2026-05-15), daily blended returns are computed as the **target-weight
    sum of each strategy's per-day return** — i.e. assuming the portfolio is
    rebalanced daily back to target. This matches how the paper-trading
    routines size positions (based on current equity, not strategy capital that
    has compounded independently). Otherwise, falls back to dollar-weighted
    returns from the un-throttled combined curve, which has a path-dependent
    bias when strategies diverge in return: B's compounded weight in the
    combined curve outgrows A and C, so its daily returns dominate the
    "blended" return that the CB scales. That bias overstates portfolio CAGR
    when B has a huge backtest tail-return (the +5,351% survivor-biased case)
    and understates it when B is reduced — exactly the symptom A3 surfaced.
    """
    thresholds = portfolio_risk.CircuitBreakerThresholds(
        half_dd=half_dd,
        out_dd=out_dd,
        half_to_full_recover_dd=recovery_dd,
        out_to_half_recover_dd=out_recover_dd,
    )
    cash_rets = {d: r for d, r in _daily_returns(shv_curve)}

    cb_state = portfolio_risk.CircuitBreakerState()
    portfolio = initial_capital
    events: list[dict] = []
    curve: list[tuple[str, float]] = []

    use_target_blend = per_strategy_curves is not None and target_weights is not None
    if use_target_blend:
        # Pre-compute per-strategy daily returns indexed by date.
        per_rets: dict[str, dict[str, float]] = {
            name: {d: r for d, r in _daily_returns(c)}
            for name, c in per_strategy_curves.items()
        }
        # Walk the date sequence from the combined curve (already aligned).
        dates_seq = [d for d, _ in strategy_combined_curve]

        for date in dates_seq:
            blended_ret = sum(
                target_weights.get(name, 0.0) * per_rets.get(name, {}).get(date, 0.0)
                for name in target_weights
            )
            throttle = portfolio_risk.exposure_fraction(cb_state.state)
            cash_ret = cash_rets.get(date, 0.0)
            port_ret = throttle * blended_ret + (1 - throttle) * cash_ret
            portfolio = portfolio * (1 + port_ret)

            result = portfolio_risk.step(cb_state, portfolio, thresholds)
            if result.transitioned:
                events.append({
                    "date": date,
                    "from": result.previous_state,
                    "to": result.new_state.state,
                    "dd_pct": result.drawdown * 100,
                    "portfolio": portfolio,
                })
            cb_state = result.new_state
            curve.append((date, portfolio))
        return curve, events

    # Legacy code path — preserved for reproducibility of historical backtest
    # outputs. Has the floating-weight bias documented above.
    strat_rets = _daily_returns(strategy_combined_curve)
    for date, strat_ret in strat_rets:
        throttle = portfolio_risk.exposure_fraction(cb_state.state)
        cash_ret = cash_rets.get(date, 0.0)
        port_ret = throttle * strat_ret + (1 - throttle) * cash_ret
        portfolio = portfolio * (1 + port_ret)

        result = portfolio_risk.step(cb_state, portfolio, thresholds)
        if result.transitioned:
            events.append({
                "date": date,
                "from": result.previous_state,
                "to": result.new_state.state,
                "dd_pct": result.drawdown * 100,
                "portfolio": portfolio,
            })
        cb_state = result.new_state
        curve.append((date, portfolio))

    return curve, events


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
# Strategy B as-of universe runner (survivor-bias stress test)
# ---------------------------------------------------------------------------

# Symbols that must NOT appear in Strategy B's universe (they belong to TAA / gold overlay).
_MACRO_ETFS: frozenset[str] = frozenset(["SPY", "IEF", "GLD", "SHV", "TLT", "SHY", "BIL"])


def run_strategy_b_as_of(
    all_bars: dict[str, list[dict]],
    *,
    start_date: str,
    end_date: str,
    initial_capital: float,
    max_position_size_pct: float = 20.0,
    strategy_rules: dict,
) -> BacktestResult:
    """Run large_cap_momentum_top5 with a year-by-year point-in-time universe.

    At each date, the candidate universe is restricted to the symbols that were
    in the S&P 100 (or top-30 by market cap) at the start of *that year*, per
    data/historical/sp100_as_of.json.  SPY bars are still available for the
    trend filter.  All other logic (momentum window, top-N selection, fill
    model, position sizing) is identical to the standard backtest.

    Returns a BacktestResult so the rest of run_backtest() can consume it
    without knowing which path was taken.
    """
    fm = FillModel()
    cash = initial_capital
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    equity_curve: list[tuple[str, float]] = []

    if "SPY" not in all_bars:
        raise ValueError("SPY bars required for Strategy B trend filter")

    # Build the date timeline from SPY.
    dates = [b["ts"][:10] for b in all_bars["SPY"]]
    start_idx = next((i for i, d in enumerate(dates) if d >= start_date), None)
    end_idx = next((i for i, d in enumerate(dates) if d > end_date), len(dates))
    if start_idx is None:
        raise ValueError(f"no SPY bars at or after start_date={start_date}")
    warmup = 200
    start_idx = max(start_idx, warmup)

    # Cache today's strategy_rules with Strategy B active.
    rules_b_active = strategy_rules

    for i in range(start_idx, end_idx):
        date = dates[i]
        # Year-appropriate universe from the as-of table.
        as_of_syms = set(historical_membership.members_as_of(date))

        # Build the per-step bars slice, restricted to as-of symbols plus SPY.
        # This is the key difference vs the standard run: symbols not in the as-of
        # set are invisible to the momentum ranker at this date.
        allowed = as_of_syms | {"SPY"}
        slice_by_symbol: dict[str, list[dict]] = {}
        for sym, sym_bars in all_bars.items():
            if sym not in allowed:
                continue
            if i < len(sym_bars):
                slice_by_symbol[sym] = sym_bars[: i + 1]

        # Also include any currently-held position even if it fell off the as-of
        # list this year — we need its bars for mark-to-market and EXIT signals.
        for held_sym in positions:
            if held_sym not in slice_by_symbol and held_sym in all_bars:
                sym_bars = all_bars[held_sym]
                if i < len(sym_bars):
                    slice_by_symbol[held_sym] = sym_bars[: i + 1]

        if "SPY" not in slice_by_symbol:
            continue

        regime = signals.detect_regime(slice_by_symbol["SPY"], None)
        # watchlist_symbols for evaluate_large_cap_momentum_top5: pass as-of symbols
        # so its universe filter sees only the year-appropriate names.
        as_of_watchlist = [s for s in as_of_syms if s in slice_by_symbol]
        strat_signals = signals.evaluate_large_cap_momentum_top5(
            slice_by_symbol, as_of_watchlist, regime, rules_b_active,
        )
        my_signals = [s for s in strat_signals
                      if s.strategy == "large_cap_momentum_top5"]

        # EXITs first (free capital).
        for sig in my_signals:
            if sig.action == "EXIT" and sig.symbol in positions:
                p = positions.pop(sig.symbol)
                bars_for_sym = slice_by_symbol.get(sig.symbol, [])
                if not bars_for_sym:
                    # Symbol no longer has data (bankruptcy / delisting): fill at 0.
                    fill_price = 0.0
                else:
                    fill_price = simulated_fill_price(
                        side="CLOSE", quote_price=float(bars_for_sym[-1]["close"]), model=fm
                    )
                proceeds = p.quantity * fill_price
                cash += proceeds
                trades.append({
                    "date": date, "symbol": sig.symbol, "side": "EXIT",
                    "quantity": p.quantity, "price": fill_price,
                    "pnl": (fill_price - p.entry_price) * p.quantity,
                    "rationale": sig.rationale,
                })

        # Force-EXIT any held position whose symbol is no longer in the as-of
        # list AND has no bars at this date (effectively delisted).
        for held_sym in list(positions.keys()):
            if held_sym not in slice_by_symbol:
                p = positions.pop(held_sym)
                cash += 0  # treat as total loss (no data = delisted at ~$0)
                trades.append({
                    "date": date, "symbol": held_sym, "side": "EXIT",
                    "quantity": p.quantity, "price": 0.0,
                    "pnl": -p.entry_price * p.quantity,
                    "rationale": "delisted / no bars: forced close at $0",
                })

        # ENTRYs.
        for sig in my_signals:
            if sig.action == "ENTRY" and sig.symbol not in positions and sig.symbol in slice_by_symbol:
                bars_for_sym = slice_by_symbol[sig.symbol]
                quote = float(bars_for_sym[-1]["close"])
                fill_price = simulated_fill_price(side="BUY", quote_price=quote, model=fm)
                equity_now = cash + sum(
                    pp.quantity * float(slice_by_symbol[s][-1]["close"])
                    for s, pp in positions.items()
                    if s in slice_by_symbol
                )
                budget = equity_now * (max_position_size_pct / 100.0)
                qty = math.floor(budget / fill_price)
                if qty <= 0 or qty * fill_price > cash:
                    continue
                cash -= qty * fill_price
                positions[sig.symbol] = Position(
                    symbol=sig.symbol, quantity=qty, entry_price=fill_price, entry_date=date,
                )
                trades.append({
                    "date": date, "symbol": sig.symbol, "side": "ENTRY",
                    "quantity": qty, "price": fill_price, "pnl": 0.0,
                    "rationale": sig.rationale,
                })

        # Mark-to-market.
        equity = cash + sum(
            pp.quantity * float(slice_by_symbol[s][-1]["close"])
            for s, pp in positions.items()
            if s in slice_by_symbol
        )
        equity_curve.append((date, equity))

    # Close any still-open positions at end-of-backtest.
    final_date = dates[end_idx - 1]
    for sym, p in list(positions.items()):
        sym_bars = all_bars.get(sym, [])
        if sym_bars and end_idx <= len(sym_bars):
            quote = float(sym_bars[end_idx - 1]["close"])
            fill_price = simulated_fill_price(side="CLOSE", quote_price=quote, model=fm)
        else:
            fill_price = 0.0
        cash += p.quantity * fill_price
        trades.append({
            "date": final_date, "symbol": sym, "side": "EXIT",
            "quantity": p.quantity, "price": fill_price,
            "pnl": (fill_price - p.entry_price) * p.quantity,
            "rationale": "end-of-backtest forced close",
        })
        positions.pop(sym)

    return BacktestResult(
        strategy="large_cap_momentum_top5",
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_equity=cash,
        trades=trades,
        equity_curve=equity_curve,
    )


# ---------------------------------------------------------------------------
# Core backtest logic (callable by sweep scripts)
# ---------------------------------------------------------------------------

def run_backtest(args) -> dict:
    """Run the full multi-strategy backtest and return a metrics dict.

    Args:
        args: Any object with the same attributes as the argparse Namespace produced
              by main(). Accepted attributes:
                start, end, capital, alloc_a, alloc_b, alloc_c,
                cash_buffer_pct, circuit_breaker,
                cb_half_dd, cb_out_dd, cb_recovery_dd, cb_out_recover_dd,
                label, write_report (optional, defaults True),
                cash_proxy (optional, defaults "SHV" — use BIL or SHY for
                            long-window backtests before SHV's 2007 listing).

    Returns a dict with keys:
        ann_return        – annualized return (%)
        max_drawdown_pct  – max drawdown (%)
        sharpe            – Sharpe ratio
        final_equity      – final portfolio equity ($)
        cb_events         – list of circuit-breaker event dicts (may be empty)
        n_trades          – total closed trades across all strategies
        equity_curve      – list of (date, portfolio_value) tuples
        overall           – bool: meets minimum targets (ann_return≥8%, dd≤15%, sharpe≥0.8)
        hit_low           – bool: ann_return ≥ TARGET_ANNUAL_RETURN_LOW
        hit_high          – bool: ann_return ≥ TARGET_ANNUAL_RETURN_HIGH
        dd_ok             – bool: max_drawdown_pct ≤ MAX_DRAWDOWN_CAP
        sharpe_ok         – bool: sharpe ≥ MIN_SHARPE
    """
    write_report = getattr(args, "write_report", True)
    cash_proxy = getattr(args, "cash_proxy", "SHV")

    if not 0.0 <= args.cash_buffer_pct < 0.95:
        raise ValueError(f"cash_buffer_pct out of range: {args.cash_buffer_pct}")

    ALLOCATION = {
        "dual_momentum_taa": args.alloc_a,
        "large_cap_momentum_top5": args.alloc_b,
        "gold_permanent_overlay": args.alloc_c,
    }
    total_alloc = sum(ALLOCATION.values())
    if abs(total_alloc - 1.0) > 0.001:
        raise ValueError(
            f"allocations sum to {total_alloc:.3f}, must equal 1.0 "
            f"(they're shares of the deployed portion; cash buffer is separate)"
        )

    deployed_frac = 1.0 - args.cash_buffer_pct
    cash_capital = args.capital * args.cash_buffer_pct
    deployed_capital = args.capital * deployed_frac

    print(f"Multi-strategy backtest")
    print(f"  Window: {args.start} → {args.end}")
    print(f"  Capital: ${args.capital:,.0f}")
    if args.cash_buffer_pct > 0:
        print(f"  Cash buffer: {args.cash_buffer_pct:.0%} (${cash_capital:,.0f} in {cash_proxy}, no rebalancing)")
        print(f"  Deployed: ${deployed_capital:,.0f}")
        print(f"  Effective allocations (of total): "
              f"A={ALLOCATION['dual_momentum_taa'] * deployed_frac:.0%} "
              f"B={ALLOCATION['large_cap_momentum_top5'] * deployed_frac:.0%} "
              f"C={ALLOCATION['gold_permanent_overlay'] * deployed_frac:.0%} "
              f"Cash={args.cash_buffer_pct:.0%}")
    else:
        print(f"  Allocations: A={ALLOCATION['dual_momentum_taa']:.0%} "
              f"B={ALLOCATION['large_cap_momentum_top5']:.0%} "
              f"C={ALLOCATION['gold_permanent_overlay']:.0%}")
    if args.label:
        print(f"  Label: {args.label}")
    print()

    watchlist = config.watchlist()
    symbols = [s["symbol"] for s in watchlist["symbols"]]

    # If a non-default cash proxy (BIL, SHY) is requested and not in the watchlist,
    # add it to the fetch list. The watchlist always has SHV.
    symbols_to_fetch = list(symbols)
    if cash_proxy not in symbols_to_fetch:
        symbols_to_fetch.append(cash_proxy)
        print(f"[fetch] adding {cash_proxy} (alternate cash proxy, not in watchlist)")

    print(f"[fetch] pulling {len(symbols_to_fetch)} symbols from yfinance...")
    bars: dict[str, list[dict]] = {}
    for sym in symbols_to_fetch:
        try:
            bars[sym] = fetch_bars_yfinance(sym)
        except Exception as exc:
            print(f"  {sym}: FAILED {exc}")
            continue
        time.sleep(0.05)

    # Drop any bars dated before a symbol's listing date.
    # yfinance occasionally returns synthesized pre-listing rows (zeros / NaN).
    # This is a no-op for symbols not in MEGACAP_LISTING_DATES, and a defensive
    # filter for META/TSLA/V in long-window (pre-2012) backtests.
    bars = filter_bars_by_listing(bars)

    # Align symbols to the window.
    # Strategy: use only symbols with data back to args.start as the "anchor" for
    # finding common trading dates. Symbols that IPO'd mid-window (META 2012,
    # TSLA 2010, V 2008) are included in bars but not in the alignment anchor set —
    # they will naturally have < momentum_window bars in early years and be
    # excluded from top-N selection by the signals layer until they have enough history.
    # This allows long-window backtests (start=2007) to work correctly even though
    # META/TSLA/V don't exist until later.
    anchor_syms = {sym for sym, b in bars.items()
                   if b and b[0]["ts"][:10] <= args.start}
    bars_anchor = {sym: b for sym, b in bars.items() if sym in anchor_syms}
    if not bars_anchor:
        # Fallback: align everything (production windows where all symbols have data)
        bars_anchor = bars
    aligned = align_bars(bars_anchor, start_date=args.start, end_date=args.end)
    if "SPY" not in aligned:
        raise RuntimeError("no SPY in aligned data")
    sample_len = len(next(iter(aligned.values())))
    sample_first = next(iter(aligned.values()))[0]["ts"][:10]
    sample_last = next(iter(aligned.values()))[-1]["ts"][:10]
    universe_size = len(aligned)

    # For symbols that IPO'd mid-window, trim their bars to the common trading-day grid
    # established by the anchor symbols. This ensures consistent date indexing.
    common_dates = {b["ts"][:10] for b in next(iter(aligned.values()))}
    for sym, sym_bars in bars.items():
        if sym not in aligned:
            aligned[sym] = [b for b in sym_bars
                            if args.start <= b["ts"][:10] <= args.end
                            and b["ts"][:10] in common_dates]

    print(f"[fetch] aligned to {sample_len} common days ({sample_first} → {sample_last}); "
          f"{len([s for s in aligned if aligned[s]])} symbols in aligned window")
    n_mid_window = len([s for s in aligned if s not in anchor_syms and aligned[s]])
    if n_mid_window:
        print(f"[fetch] {n_mid_window} symbols IPO'd mid-window; "
              f"excluded from early-year top-N via bars-length gate in signals layer")

    # Some large-cap stocks may IPO mid-window. They drop out of alignment, which biases the
    # large-cap-momentum universe toward survivors with the longest history. For 2005+ we
    # may lose META (IPO 2012), V (IPO 2008), TSLA (IPO 2010), MA (IPO 2006).
    if universe_size < 8:
        print(f"[fetch] WARNING: only {universe_size} anchor symbols in aligned window — "
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
        raise RuntimeError(f"only {sample_len} days, need > {warmup} for warmup")
    start_date = next(iter(aligned.values()))[warmup]["ts"][:10]
    end_date = sample_last

    # --- Strategy A: dual_momentum_taa ---
    cap_a = deployed_capital * ALLOCATION["dual_momentum_taa"]
    print(f"\n[strategy A] dual_momentum_taa ${cap_a:,.0f}...")
    sma_months = args.sma_months
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
        strategy_params={"dual_momentum_taa": {"ma_window_days": sma_months * 21}},
    )
    print(f"  done in {time.time() - t0:.1f}s; "
          f"return {result_a.total_return_pct:+.2f}%, trades {len(result_a.trades)}")

    # --- Strategy B: large_cap_momentum_top5 ---
    cap_b = deployed_capital * ALLOCATION["large_cap_momentum_top5"]
    universe_mode = getattr(args, "strategy_b_universe_mode", "modern")
    print(f"\n[strategy B] large_cap_momentum_top5 ${cap_b:,.0f} (universe={universe_mode})...")
    t0 = time.time()
    if universe_mode == "as_of":
        # Survivor-bias stress-test path: fetch bars for every symbol that ever
        # appeared in the as-of universe table, align them to the common-date grid,
        # then run a per-date filtered backtest.
        as_of_all_syms = historical_membership.all_known_symbols()
        extra_needed = [s for s in as_of_all_syms if s not in aligned]
        if extra_needed:
            print(f"  [as_of] fetching {len(extra_needed)} additional as-of symbols...")
        as_of_bars: dict[str, list[dict]] = dict(aligned)  # start with existing aligned bars
        for sym in extra_needed:
            try:
                raw = fetch_bars_yfinance(sym)
                if raw:
                    # Filter to the common-date grid established by the anchor symbols.
                    common_dates = {b["ts"][:10] for b in next(iter(aligned.values()))}
                    as_of_bars[sym] = [b for b in raw
                                       if args.start <= b["ts"][:10] <= args.end
                                       and b["ts"][:10] in common_dates]
            except Exception as exc:
                print(f"  [as_of] {sym}: FAILED {exc}")
            time.sleep(0.05)
        print(f"  [as_of] universe pool: {len(as_of_bars)} symbols total")
        result_b = run_strategy_b_as_of(
            as_of_bars,
            start_date=start_date,
            end_date=end_date,
            initial_capital=cap_b,
            max_position_size_pct=20.0,
            strategy_rules=rules,
        )
    else:
        result_b = backtest.run_backtest(
            strategy="large_cap_momentum_top5",
            bars_by_symbol=aligned,
            watchlist_symbols=symbols,
            strategy_rules=rules,
            start_date=start_date,
            end_date=end_date,
            initial_capital=cap_b,
            max_position_size_pct=20.0,  # 5 positions = 20% each of strategy B capital
            # Strategy B's rank-by-return signal needs the exact official close
            # (per the MOC signal-proxy gate), so it cannot fill at that close.
            # next_open models realistic execution: decide on close[D], fill at
            # open[D+1]. A and C keep the default close fill (validated for MOC).
            fill_timing=getattr(args, "strategy_b_fill", "close"),
        )
    print(f"  done in {time.time() - t0:.1f}s; "
          f"return {result_b.total_return_pct:+.2f}%, trades {len(result_b.trades)}")

    # --- Strategy C: gold_permanent_overlay ---
    cap_c = deployed_capital * ALLOCATION["gold_permanent_overlay"]
    print(f"\n[strategy C] gold_permanent_overlay ${cap_c:,.0f}...")
    result_c = run_strategy_c_gld_permanent(
        aligned, start_date=start_date, end_date=end_date, capital=cap_c,
    )
    final_c = result_c["final_equity"]
    return_c = (final_c / cap_c - 1) * 100
    print(f"  return {return_c:+.2f}%")

    # --- Cash bucket: cash proxy buy-and-hold for the cash buffer portion ---
    result_cash = {"equity_curve": [], "final_equity": 0.0}
    return_cash = 0.0
    if args.cash_buffer_pct > 0 and cash_capital > 0:
        print(f"\n[cash bucket] {cash_proxy} buy-and-hold ${cash_capital:,.0f}...")
        result_cash = run_cash_bucket_shv(
            aligned, start_date=start_date, end_date=end_date, capital=cash_capital,
            cash_proxy=cash_proxy,
        )
        if result_cash["final_equity"] > 0:
            return_cash = (result_cash["final_equity"] / cash_capital - 1) * 100
            print(f"  return {return_cash:+.2f}% (treasury bills via {cash_proxy})")

    # --- Portfolio combine ---
    curves_to_combine = [
        result_a.equity_curve,
        result_b.equity_curve,
        result_c["equity_curve"],
    ]
    if result_cash["equity_curve"]:
        curves_to_combine.append(result_cash["equity_curve"])
    portfolio_curve = _combine_equity_curves(curves_to_combine)
    if not portfolio_curve:
        raise RuntimeError("empty portfolio curve")

    # --- Optional circuit-breaker pass ---
    cb_events: list[dict] = []
    if args.circuit_breaker:
        # Strategy-only combined curve (without the cash buffer); CB manages cash itself.
        strategy_only_curve = _combine_equity_curves([
            result_a.equity_curve,
            result_b.equity_curve,
            result_c["equity_curve"],
        ])
        # Cash proxy reference curve on $1 of capital — only used for daily returns inside CB.
        shv_ref = run_cash_bucket_shv(
            aligned, start_date=start_date, end_date=end_date, capital=1.0,
            cash_proxy=cash_proxy,
        )["equity_curve"]
        # CB starts with the deployed capital (strategy capital), not args.capital,
        # so the cash buffer (if any) is preserved and added back at the end.
        #
        # By default (2026-05-15+) the CB blends per-strategy daily returns
        # using target weights — i.e. it simulates daily rebalancing back to
        # the target alloc-a/b/c. The legacy floating-weight code path is
        # available via --legacy-cb-blend for reproducing pre-fix backtests.
        cb_per_strategy = None
        cb_target_weights = None
        if not getattr(args, "legacy_cb_blend", False):
            cb_per_strategy = {
                "dual_momentum_taa": result_a.equity_curve,
                "large_cap_momentum_top5": result_b.equity_curve,
                "gold_permanent_overlay": result_c["equity_curve"],
            }
            cb_target_weights = dict(ALLOCATION)
        cb_curve, cb_events = apply_circuit_breaker(
            strategy_only_curve,
            shv_ref,
            initial_capital=deployed_capital,
            half_dd=args.cb_half_dd,
            out_dd=args.cb_out_dd,
            recovery_dd=args.cb_recovery_dd,
            out_recover_dd=args.cb_out_recover_dd,
            per_strategy_curves=cb_per_strategy,
            target_weights=cb_target_weights,
        )
        # Rebuild portfolio_curve = circuit-broken deployed leg + (optional) cash buffer leg.
        date_to_cb = dict(cb_curve)
        if result_cash["equity_curve"]:
            new_curve = []
            for date, cash_val in result_cash["equity_curve"]:
                new_curve.append((date, date_to_cb.get(date, 0.0) + cash_val))
            portfolio_curve = new_curve
        else:
            portfolio_curve = cb_curve
        print(f"\n[circuit-breaker] thresholds: HALF@{args.cb_half_dd:.1%} "
              f"OUT@{args.cb_out_dd:.1%} HALF→FULL@{args.cb_recovery_dd:.1%} "
              f"OUT→HALF@{args.cb_out_recover_dd:.1%}")
        print(f"[circuit-breaker] {len(cb_events)} throttle events"
              if cb_events else "[circuit-breaker] no triggers in window")
        for ev in cb_events[:20]:
            print(f"  {ev['date']}  {ev['from']:>4} → {ev['to']:<4}  "
                  f"DD={ev['dd_pct']:.2f}%  port=${ev['portfolio']:,.0f}")
        if len(cb_events) > 20:
            print(f"  ... {len(cb_events) - 20} more events (see report)")

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
    print(f"    A (TAA):            ${result_a.final_equity:>12,.2f}  "
          f"(return {result_a.total_return_pct:+.2f}%)")
    print(f"    B (large-cap mom):  ${result_b.final_equity:>12,.2f}  "
          f"(return {result_b.total_return_pct:+.2f}%)")
    print(f"    C (gold overlay):   ${final_c:>12,.2f}  "
          f"(return {return_c:+.2f}%)")
    if args.cash_buffer_pct > 0:
        print(f"    Cash (SHV):         ${result_cash['final_equity']:>12,.2f}  "
              f"(return {return_cash:+.2f}%)")
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
    print(f"  Live-trading unlock: requires the same targets met in paper trading for "
          f"90+ days AND 30+ closed trades, plus a signed PR to docs/risk_profile.md.")

    # --- Write report (skip when write_report=False) ---
    if write_report:
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
            f"- Cash proxy: {cash_proxy} (used for Strategy A cash floor and cash buffer)",
            f"- Cash buffer: {args.cash_buffer_pct:.0%} (${cash_capital:,.0f} in {cash_proxy}, static — no rebalancing)",
            f"- Deployed: ${deployed_capital:,.0f}",
            "",
            "| Strategy | Allocation (of total) | Return | Final equity | Trades |",
            "|---|---:|---:|---:|---:|",
            f"| dual_momentum_taa | {ALLOCATION['dual_momentum_taa'] * deployed_frac:.1%} | "
            f"{result_a.total_return_pct:+.2f}% | ${result_a.final_equity:,.2f} | "
            f"{sum(1 for t in result_a.trades if t['side'] == 'EXIT')} |",
            f"| large_cap_momentum_top5 | {ALLOCATION['large_cap_momentum_top5'] * deployed_frac:.1%} | "
            f"{result_b.total_return_pct:+.2f}% | ${result_b.final_equity:,.2f} | "
            f"{sum(1 for t in result_b.trades if t['side'] == 'EXIT')} |",
            f"| gold_permanent_overlay | {ALLOCATION['gold_permanent_overlay'] * deployed_frac:.1%} | "
            f"{return_c:+.2f}% | ${final_c:,.2f} | "
            f"{sum(1 for t in result_c['trades'] if t['side'] == 'EXIT')} |",
            *(
                [f"| cash_buffer_{cash_proxy.lower()} | {args.cash_buffer_pct:.1%} | "
                 f"{return_cash:+.2f}% | ${result_cash['final_equity']:,.2f} | 0 |"]
                if args.cash_buffer_pct > 0 else []
            ),
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
            *(
                [
                    "## Circuit-breaker",
                    f"- Thresholds: FULL → HALF @ {args.cb_half_dd:.1%} DD, "
                    f"HALF → OUT @ {args.cb_out_dd:.1%} DD, "
                    f"HALF → FULL @ {args.cb_recovery_dd:.1%} DD, "
                    f"OUT → HALF @ {args.cb_out_recover_dd:.1%} DD.",
                    f"- Throttle events: {len(cb_events)} over the window.",
                    "",
                    "| Date | From | To | Drawdown | Portfolio |",
                    "|---|---|---|---:|---:|",
                    *[f"| {ev['date']} | {ev['from']} | {ev['to']} | "
                      f"{ev['dd_pct']:.2f}% | ${ev['portfolio']:,.0f} |"
                      for ev in cb_events],
                    "",
                ]
                if args.circuit_breaker else []
            ),
            "## Caveats",
            "- Backtest uses yfinance survivor-biased current S&P 100 large-cap universe;",
            "  large_cap_momentum_top5 results are optimistic for periods where losers were excluded.",
            "- Includes ~4 bps round-trip friction (1bp slippage + 1bp half-spread per side).",
            "- No tax modeling — real-world returns would be lower for short-term gains.",
            "- 12-month momentum warmup means actual trading window is "
            f"{warmup} days shorter than the calendar window.",
            *(
                ["- Cash buffer is STATIC (no rebalancing). As strategies compound, the cash share of "
                 "the portfolio shrinks, so its DD protection weakens in later years. A rebalanced "
                 "variant would have lower returns and lower DD."]
                if args.cash_buffer_pct > 0 else []
            ),
            *(
                [f"- Circuit-breaker is post-hoc on daily returns: the throttle scales today's "
                 f"strategy-leg contribution to portfolio return; the cash leg earns {cash_proxy}'s daily "
                 f"return. This is an approximation — a true live circuit-breaker would execute "
                 f"rebalance trades on the day of the trigger and pay friction. Real-world results "
                 f"would be marginally worse (a few bps per transition)."]
                if args.circuit_breaker else []
            ),
        ]
        report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  Report: {report_file.relative_to(REPO_ROOT)}")

    n_trades = (
        sum(1 for t in result_a.trades if t["side"] == "EXIT")
        + sum(1 for t in result_b.trades if t["side"] == "EXIT")
        + sum(1 for t in result_c["trades"] if t["side"] == "EXIT")
    )

    return {
        "ann_return": ann_return,
        "max_drawdown_pct": mdd,
        "sharpe": sharpe,
        "final_equity": final_equity,
        "cb_events": cb_events,
        "n_trades": n_trades,
        "equity_curve": portfolio_curve,
        "overall": overall,
        "hit_low": hit_low,
        "hit_high": hit_high,
        "dd_ok": dd_ok,
        "sharpe_ok": sharpe_ok,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
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
    parser.add_argument("--cash-buffer-pct", type=float, default=0.0,
                        help="Fraction of total capital held as a cash buffer (0-0.95). "
                             "alloc-a/b/c are interpreted as shares of the deployed portion "
                             "and must still sum to 1.0; their effective share of total capital "
                             "is alloc_i * (1 - cash_buffer_pct).")
    parser.add_argument("--cash-proxy", default="SHV", choices=["SHV", "BIL", "SHY"],
                        help="Cash proxy for Strategy A cash floor and cash-bucket allocation. "
                             "Use BIL or SHY for windows that start before SHV's 2007-01-11 listing. "
                             "BIL (launched 2007-05-30) and SHY (launched 2002-07-26) are short-T-bill "
                             "equivalents with slightly different yield characteristics. Default: SHV.")
    parser.add_argument("--legacy-cb-blend", action="store_true",
                        help="Use the pre-2026-05-15 floating-weight blend in the circuit-breaker "
                             "(daily returns derived from the un-throttled combined curve). "
                             "Has a path-dependent bias that overstates portfolio CAGR when one "
                             "strategy has a huge backtest tail-return. Kept for reproducing "
                             "historical backtests; new runs should omit this flag.")
    parser.add_argument("--circuit-breaker", action="store_true",
                        help="Apply portfolio-level drawdown circuit-breaker. Throttle state "
                             "machine: FULL (100%% strategies) → HALF (50%%) at --cb-half-dd → "
                             "OUT (0%%) at --cb-out-dd. Recover to FULL when DD ≤ --cb-recovery-dd. "
                             "When throttled, the remainder sits in the cash proxy.")
    parser.add_argument("--cb-half-dd", type=float, default=0.08,
                        help="Drawdown that trips FULL → HALF (default 0.08 = 8%%).")
    parser.add_argument("--cb-out-dd", type=float, default=0.12,
                        help="Drawdown that trips HALF → OUT (default 0.12 = 12%%).")
    parser.add_argument("--cb-recovery-dd", type=float, default=0.05,
                        help="Drawdown below which HALF → FULL (default 0.05 = 5%%). "
                             "Provides hysteresis vs the 8%% HALF trigger.")
    parser.add_argument("--cb-out-recover-dd", type=float, default=0.08,
                        help="Drawdown below which OUT → HALF (default 0.08 = 8%%). "
                             "Asymmetric vs cb-recovery-dd: tight hysteresis around HALF, "
                             "fast recovery from OUT.")
    parser.add_argument("--sma-months", type=int, default=10,
                        help="Strategy A trend-filter SMA window in months (default 10). "
                             "21 trading days per month; 10 → 210-day SMA (Faber TAA default).")
    parser.add_argument("--strategy-b-universe-mode", default="modern",
                        choices=["modern", "as_of"],
                        dest="strategy_b_universe_mode",
                        help="'modern' (default): present-day watchlist mega-caps. "
                             "'as_of': year-by-year point-in-time S&P 100 membership from "
                             "data/historical/sp100_as_of.json. Used by the survivor-bias "
                             "stress test to measure how much of Strategy B's edge comes "
                             "from selecting today's mega-cap survivors vs the actual "
                             "large-cap basket that existed at each date.")
    parser.add_argument("--strategy-b-fill", default="close",
                        choices=["close", "next_open"],
                        dest="strategy_b_fill",
                        help="Fill timing for Strategy B only (A/C always fill "
                             "at the close, validated for MOC). 'close' "
                             "(default) reproduces the canonical baseline. "
                             "'next_open' models realistic execution after the "
                             "MOC signal-proxy gate showed B's ranking needs "
                             "the exact close: decide on close[D], fill at "
                             "open[D+1].")
    parser.add_argument("--label", default="",
                        help="Optional tag included in the report filename")
    parser.add_argument("--no-report", dest="write_report", action="store_false",
                        help="Skip writing the markdown report (used by sweep scripts)")
    parser.set_defaults(write_report=True)
    args = parser.parse_args()
    result = run_backtest(args)
    return 0 if result["overall"] else 1


if __name__ == "__main__":
    sys.exit(main())
