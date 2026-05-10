"""Deterministic backtest harness.

Replays bars chronologically and applies `lib.signals` rules at each step.
Tracks paper-portfolio equity, computes performance metrics vs SPY and vs equal-weight
sector buy-and-hold, and writes a markdown report under `backtests/<strategy>/<date>.md`.

Hard rule: this is the **prerequisite** for any strategy to advance from
NEEDS_MORE_DATA to ACTIVE_PAPER_TEST in `config/strategy_rules.yaml`.

For v1 we deliberately keep the harness simple — no vectorbt dependency yet, just a
pure-Python event loop. Easy to inspect, easy to verify, slow but fine on years of
daily bars across 12 ETFs.

Usage:
    from lib.backtest import run_backtest, write_report
    result = run_backtest(strategy="sector_relative_strength_rotation",
                          bars_by_symbol=..., start_date=..., end_date=...,
                          initial_capital=100000.0)
    write_report(result, output_dir="backtests/sector_relative_strength_rotation")
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from lib import indicators, signals
from lib.fills import FillModel, simulated_fill_price


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    entry_date: str


@dataclass
class BacktestResult:
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    benchmark_curves: dict[str, list[tuple[str, float]]] = field(default_factory=dict)

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.initial_capital - 1) * 100

    @property
    def num_trades(self) -> int:
        return sum(1 for t in self.trades if t["side"] == "EXIT")


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _returns_from_curve(curve: list[tuple[str, float]]) -> list[float]:
    rets: list[float] = []
    for i in range(1, len(curve)):
        prev = curve[i - 1][1]
        cur = curve[i][1]
        if prev > 0:
            rets.append(cur / prev - 1)
    return rets


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _max_drawdown(curve: list[tuple[str, float]]) -> float:
    """Max drawdown as a positive fraction (0.10 = 10% drawdown)."""
    if not curve:
        return 0.0
    peak = curve[0][1]
    mdd = 0.0
    for _, v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def _annualized_sharpe(rets: list[float], periods_per_year: int = 252) -> float:
    if not rets:
        return 0.0
    mean = sum(rets) / len(rets)
    sd = _stdev(rets)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(periods_per_year)


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def run_backtest(*, strategy: str,
                 bars_by_symbol: dict[str, list[dict]],
                 watchlist_symbols: list[str],
                 strategy_rules: dict,
                 start_date: str,
                 end_date: str,
                 initial_capital: float = 100_000.0,
                 max_position_size_pct: float = 25.0,
                 fill_model: FillModel | None = None) -> BacktestResult:
    """Run an event-driven backtest of a single named strategy.

    `bars_by_symbol` must contain bars for SPY, all watchlist symbols, and (optionally)
    a synthetic VIX series under key `_VIX` (for regime detection). All bar lists must
    be sorted oldest-first and aligned on common dates.
    """
    if "SPY" not in bars_by_symbol:
        raise ValueError("backtest requires SPY bars for benchmark + regime")

    fm = fill_model or FillModel()
    cash = initial_capital
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    equity_curve: list[tuple[str, float]] = []

    # Build a date index from SPY (canonical timeline).
    dates = [b["ts"][:10] for b in bars_by_symbol["SPY"]]
    start_idx = next((i for i, d in enumerate(dates) if d >= start_date), None)
    end_idx = next((i for i, d in enumerate(dates) if d > end_date), len(dates))
    if start_idx is None:
        raise ValueError(f"no bars at or after start_date={start_date}")

    # We need a warm-up window for indicators. SMA(200) needs 200 prior bars.
    warmup = 200
    start_idx = max(start_idx, warmup)

    for i in range(start_idx, end_idx):
        date = dates[i]
        # Slice each symbol's bars up to and including i.
        slice_by_symbol = {
            sym: bars[: i + 1] for sym, bars in bars_by_symbol.items()
            if i < len(bars)
        }
        spy_close = float(slice_by_symbol["SPY"][-1]["close"])
        vix_value: float | None = None
        if "_VIX" in slice_by_symbol and slice_by_symbol["_VIX"]:
            vix_value = float(slice_by_symbol["_VIX"][-1]["close"])

        regime = signals.detect_regime(slice_by_symbol["SPY"], vix_value)
        all_signals = signals.evaluate_all(
            slice_by_symbol, watchlist_symbols, regime, strategy_rules,
        )
        # Filter to the strategy under test.
        my_signals = [s for s in all_signals if s.strategy == strategy]

        # Process EXITs first to free capital.
        for sig in my_signals:
            if sig.action == "EXIT" and sig.symbol in positions:
                p = positions.pop(sig.symbol)
                bars_for_sym = slice_by_symbol[sig.symbol]
                quote = float(bars_for_sym[-1]["close"])
                fill_price = simulated_fill_price(side="CLOSE", quote_price=quote, model=fm)
                proceeds = p.quantity * fill_price
                cash += proceeds
                trades.append({
                    "date": date, "symbol": sig.symbol, "side": "EXIT",
                    "quantity": p.quantity, "price": fill_price,
                    "pnl": (fill_price - p.entry_price) * p.quantity,
                    "rationale": sig.rationale,
                })

        # Then ENTRYs.
        for sig in my_signals:
            if sig.action == "ENTRY" and sig.symbol not in positions and sig.symbol in slice_by_symbol:
                bars_for_sym = slice_by_symbol[sig.symbol]
                quote = float(bars_for_sym[-1]["close"])
                fill_price = simulated_fill_price(side="BUY", quote_price=quote, model=fm)
                # Equity now (cash + value of any still-open positions).
                equity_now = cash + sum(
                    pp.quantity * float(slice_by_symbol[s][-1]["close"])
                    for s, pp in positions.items()
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

        # Mark-to-market equity at end of bar.
        equity = cash + sum(
            pp.quantity * float(slice_by_symbol[s][-1]["close"])
            for s, pp in positions.items()
        )
        equity_curve.append((date, equity))

    # Close any open positions at the final close.
    final_date = dates[end_idx - 1]
    final_slice = {sym: bars[: end_idx] for sym, bars in bars_by_symbol.items()
                   if end_idx <= len(bars)}
    for sym, p in list(positions.items()):
        quote = float(final_slice[sym][-1]["close"])
        fill_price = simulated_fill_price(side="CLOSE", quote_price=quote, model=fm)
        cash += p.quantity * fill_price
        trades.append({
            "date": final_date, "symbol": sym, "side": "EXIT",
            "quantity": p.quantity, "price": fill_price,
            "pnl": (fill_price - p.entry_price) * p.quantity,
            "rationale": "end-of-backtest forced close",
        })
        positions.pop(sym)

    final_equity = cash
    # Build benchmarks: SPY buy-and-hold and equal-weight sector buy-and-hold.
    benchmarks: dict[str, list[tuple[str, float]]] = {}
    spy_bars_window = bars_by_symbol["SPY"][start_idx:end_idx]
    if spy_bars_window:
        spy_start_close = float(spy_bars_window[0]["close"])
        benchmarks["SPY"] = [
            (b["ts"][:10], initial_capital * float(b["close"]) / spy_start_close)
            for b in spy_bars_window
        ]
    sector_syms = [s for s in watchlist_symbols if s != "SPY"]
    if sector_syms:
        per_sector_alloc = initial_capital / len(sector_syms)
        ew_curve: list[tuple[str, float]] = []
        for j in range(start_idx, end_idx):
            equity = 0.0
            for sym in sector_syms:
                bars = bars_by_symbol.get(sym, [])
                if j >= len(bars):
                    continue
                start_close = float(bars[start_idx]["close"]) if start_idx < len(bars) else None
                cur_close = float(bars[j]["close"])
                if start_close and start_close > 0:
                    equity += per_sector_alloc * (cur_close / start_close)
            ew_curve.append((dates[j], equity))
        benchmarks["SECTOR_EW"] = ew_curve

    return BacktestResult(
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
        benchmark_curves=benchmarks,
    )


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(result: BacktestResult, *, output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fname = out / f"{result.start_date}_to_{result.end_date}.md"

    rets = _returns_from_curve(result.equity_curve)
    sharpe = _annualized_sharpe(rets)
    mdd = _max_drawdown(result.equity_curve) * 100

    spy_curve = result.benchmark_curves.get("SPY", [])
    ew_curve = result.benchmark_curves.get("SECTOR_EW", [])
    spy_return = (spy_curve[-1][1] / result.initial_capital - 1) * 100 if spy_curve else None
    ew_return = (ew_curve[-1][1] / result.initial_capital - 1) * 100 if ew_curve else None
    spy_mdd = _max_drawdown(spy_curve) * 100 if spy_curve else None

    wins = [t for t in result.trades if t["side"] == "EXIT" and t["pnl"] > 0]
    losses = [t for t in result.trades if t["side"] == "EXIT" and t["pnl"] < 0]
    total_exits = sum(1 for t in result.trades if t["side"] == "EXIT")
    win_rate = (len(wins) / total_exits * 100) if total_exits else 0.0
    avg_gain = (sum(t["pnl"] for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
    profit_factor = (sum(t["pnl"] for t in wins) / -sum(t["pnl"] for t in losses)) if losses else None

    lines: list[str] = [
        f"# Backtest — {result.strategy}",
        f"_{result.start_date} → {result.end_date}_",
        "",
        "## Result summary",
        f"- Initial capital: ${result.initial_capital:,.2f}",
        f"- Final equity: ${result.final_equity:,.2f}",
        f"- Total return: {result.total_return_pct:+.2f}%",
        f"- Annualized Sharpe (rough): {sharpe:.2f}",
        f"- Max drawdown: {mdd:.2f}%",
        f"- Trades closed: {total_exits} (W: {len(wins)} / L: {len(losses)})",
        f"- Win rate: {win_rate:.1f}%",
        f"- Avg gain: ${avg_gain:,.2f} | Avg loss: ${avg_loss:,.2f}",
        f"- Profit factor: {profit_factor:.2f}" if profit_factor else "- Profit factor: n/a",
        "",
        "## Benchmarks",
        f"- SPY buy-and-hold: {spy_return:+.2f}% (max DD {spy_mdd:.2f}%)" if spy_return is not None else "- SPY buy-and-hold: n/a",
        f"- Equal-weight sector buy-and-hold: {ew_return:+.2f}%" if ew_return is not None else "- Equal-weight sector buy-and-hold: n/a",
        f"- **Alpha vs SPY: {(result.total_return_pct - (spy_return or 0)):+.2f}%**" if spy_return is not None else "",
        f"- **Alpha vs equal-weight: {(result.total_return_pct - (ew_return or 0)):+.2f}%**" if ew_return is not None else "",
        f"- Risk-adjusted check: drawdown {'≤' if (spy_mdd is not None and mdd <= spy_mdd) else '>'} SPY's drawdown ({mdd:.2f}% vs {spy_mdd:.2f}%)" if spy_mdd is not None else "",
        "",
        "## Sample size guardrails",
        f"- Trades: {total_exits}. {'OK for evaluation' if total_exits >= 30 else 'PRELIMINARY — N < 30 trades.'}",
        "",
        "## Promotion criteria",
        "Strategy may advance from NEEDS_MORE_DATA → ACTIVE_PAPER_TEST only if **all** hold:",
        f"- Total return ≥ equal-weight benchmark: {(result.total_return_pct >= (ew_return or 0)) if ew_return is not None else '(n/a)'}",
        f"- Max drawdown ≤ SPY's max drawdown: {(mdd <= (spy_mdd or 0)) if spy_mdd is not None else '(n/a)'}",
        f"- N trades ≥ 30: {total_exits >= 30}",
        f"- Sharpe > 0: {sharpe > 0}",
        "",
        "## Trades",
        "| Date | Symbol | Side | Qty | Price | PnL | Rationale |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for t in result.trades[-200:]:  # cap output for readability
        lines.append(
            f"| {t['date']} | {t['symbol']} | {t['side']} | "
            f"{t['quantity']:.0f} | {t['price']:.2f} | "
            f"{t['pnl']:+.2f} | {t['rationale']} |"
        )

    fname.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fname
