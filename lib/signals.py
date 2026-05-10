"""Deterministic strategy signal generation — pivoted 2026-05-10.

After backtest evidence rejected long-only sector rotation across three regimes
(see reports/learning/backtest_findings_2026-05-10.md), the system pivoted to a
3-strategy retail multi-strategy framework targeting **8-10% annual absolute return
with max drawdown ≤ 15%**, not "beat SPY."

Strategies:
  A. dual_momentum_taa — trend-following across SPY/TLT/GLD/SHV; cash floor
  B. large_cap_momentum_top5 — hold top 5 by 6-month return from a curated large-cap list
  C. gold_permanent_overlay — permanent 10% GLD allocation (deterministic, no signal logic)

Each strategy is independently backtestable. The portfolio combiner in
`scripts/run_multi_strategy_backtest.py` allocates capital across them
(default 60% / 30% / 10%) and reports portfolio-level metrics.

LLM role: research/regime context, never decision-making. All entry/exit decisions
originate from this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from lib import indicators

# Strategy A universe (broad asset classes).
# IEF (7-10y treasuries) replaced TLT (20+y treasuries) on 2026-05-10 — see
# reports/learning/pivot_validation_2026-05-10.md. TLT contributed too much to
# portfolio drawdown during the 2022 rate-hike cycle (TLT fell ~30%).
TAA_RISK_ASSETS = ["SPY", "IEF", "GLD"]
TAA_CASH_PROXY = "SHV"


@dataclass
class Signal:
    symbol: str
    action: str  # ENTRY | HOLD | EXIT | NO_SIGNAL
    strategy: str
    confidence_inputs: dict[str, Any]
    confirmations_passed: list[str]
    confirmations_failed: list[str]
    rationale: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class RegimeReading:
    regime: str
    confidence: str
    indicators: dict[str, Any]
    counter_evidence: list[str]


# ---------------------------------------------------------------------------
# Regime detection (unchanged from prior version — useful for LLM context, not
# load-bearing for the new strategies' entry/exit logic).
# ---------------------------------------------------------------------------

def detect_regime(spy_bars: list[dict], vix_value: float | None,
                  sector_rs: dict[str, float] | None = None) -> RegimeReading:
    """Classify the current market regime. Same logic as prior version; retained
    because the LLM macro_sector agent still consumes it for narrative context.

    Trade decisions in the new framework do NOT depend on regime — they depend on
    the per-strategy rules below. Regime is a risk-overlay signal, not a gate.
    """
    closes = indicators.closes(spy_bars)
    spy_above_50 = indicators.above_sma(closes, 50)
    spy_above_200 = indicators.above_sma(closes, 200)
    spy_pct_50 = indicators.pct_from_sma(closes, 50)

    proxy_vol: float | None = None
    if len(closes) >= 21:
        rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes))]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        proxy_vol = (var ** 0.5) * (252 ** 0.5) * 100

    effective_vix = vix_value if vix_value is not None else proxy_vol

    inds: dict[str, Any] = {
        "spy_above_50dma": spy_above_50,
        "spy_above_200dma": spy_above_200,
        "spy_pct_from_50dma": spy_pct_50,
        "vix": vix_value,
        "proxy_vol_20d_annualized_pct": proxy_vol,
        "effective_vix_used": effective_vix,
    }

    if effective_vix is not None and effective_vix > 30:
        return RegimeReading("liquidity_stress", "high", inds,
                             counter_evidence=["VIX/proxy could spike-and-revert"])
    if effective_vix is not None and effective_vix > 22:
        return RegimeReading("high_vol", "medium", inds,
                             counter_evidence=["High vol without breadth deterioration may be transient"])
    if spy_above_50 and spy_above_200 and effective_vix is not None and effective_vix < 18:
        return RegimeReading("bullish_trend", "medium", inds,
                             counter_evidence=["Trend can break on macro shocks"])
    if spy_above_50 is False and spy_above_200 is False:
        return RegimeReading("bearish_trend", "medium", inds,
                             counter_evidence=["Bounce off 200DMA possible"])
    if (spy_above_50 is not None
        and effective_vix is not None and 13 <= effective_vix <= 22):
        return RegimeReading("range_bound", "low", inds,
                             counter_evidence=["Could break out either direction"])
    return RegimeReading("uncertain", "low", inds, counter_evidence=["Insufficient signal coherence"])


# ---------------------------------------------------------------------------
# Helper: monthly rebalance trigger
# ---------------------------------------------------------------------------

def _is_rebalance_day(today_iso: str, last_rebalance_iso: str | None,
                      min_days_between: int = 21) -> bool:
    """Roughly monthly rebalancing — fire when at least `min_days_between` calendar
    days have passed since the last rebalance. Caller tracks the last date in
    portfolio state (e.g., positions.json metadata)."""
    if not last_rebalance_iso:
        return True
    today = datetime.fromisoformat(today_iso.replace("Z", "+00:00").replace("T00:00:00+00:00", "T00:00:00+00:00"))
    last = datetime.fromisoformat(last_rebalance_iso.replace("Z", "+00:00").replace("T00:00:00+00:00", "T00:00:00+00:00"))
    return (today - last).days >= min_days_between


# ---------------------------------------------------------------------------
# Strategy A: dual_momentum_taa
# ---------------------------------------------------------------------------

def evaluate_dual_momentum_taa(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
    params: dict | None = None,
) -> list[Signal]:
    """Antonacci-style dual momentum across SPY/TLT/GLD with cash floor (SHV).

    Rule book (deterministic):
      1. For each of {SPY, TLT, GLD}: compute 12-month total return AND check
         price > 10-month SMA. Symbols failing the SMA filter are excluded.
      2. Compare survivors' 12m returns to SHV's 12m return (cash floor).
      3. Hold the single survivor with the highest 12m return.
      4. If no asset clears both filters, hold SHV (cash equivalent).

    Optional params:
      momentum_window_days: int = 252      # ~12 months of trading days
      ma_window_days: int = 210            # ~10 months
      max_holdings: int = 1                # 1 = pure dual momentum; >1 = diversified
    """
    p = params or {}
    momentum_window = int(p.get("momentum_window_days", 252))
    ma_window = int(p.get("ma_window_days", 210))
    max_holdings = int(p.get("max_holdings", 1))

    name = "dual_momentum_taa"
    required = TAA_RISK_ASSETS + [TAA_CASH_PROXY]
    missing = [s for s in required if s not in bars_by_symbol]
    if missing:
        return []

    cash_closes = indicators.closes(bars_by_symbol[TAA_CASH_PROXY])
    if len(cash_closes) < momentum_window + 1:
        return []
    cash_return = (cash_closes[-1] / cash_closes[-momentum_window - 1]) - 1.0

    candidates: list[tuple[str, float, bool, float]] = []
    for sym in TAA_RISK_ASSETS:
        if sym not in bars_by_symbol:
            continue
        c = indicators.closes(bars_by_symbol[sym])
        if len(c) < max(momentum_window, ma_window) + 1:
            continue
        ret_12m = (c[-1] / c[-momentum_window - 1]) - 1.0
        above_ma = indicators.above_sma(c, ma_window) or False
        candidates.append((sym, ret_12m, above_ma, ret_12m - cash_return))

    qualified = [c for c in candidates if c[2] and c[3] > 0]
    qualified.sort(key=lambda x: x[1], reverse=True)
    winners = {c[0] for c in qualified[:max_holdings]}

    signals: list[Signal] = []
    inputs_summary = {
        "cash_return_12m": cash_return,
        "candidates": [
            {"symbol": s, "ret_12m": r, "above_10m_ma": a, "vs_cash": v}
            for (s, r, a, v) in candidates
        ],
        "winners": sorted(winners),
    }

    # ENTRY/EXIT signals for each risk asset.
    for sym in TAA_RISK_ASSETS:
        if sym not in bars_by_symbol:
            continue
        c = indicators.closes(bars_by_symbol[sym])
        passed: list[str] = []
        failed: list[str] = []
        ret_12m_record = next((r for (s, r, _, _) in candidates if s == sym), None)
        above_ma_record = next((a for (s, _, a, _) in candidates if s == sym), False)
        if above_ma_record:
            passed.append(f"{sym} above {ma_window}d MA")
        else:
            failed.append(f"{sym} below {ma_window}d MA")
        if ret_12m_record is not None and ret_12m_record > cash_return:
            passed.append(f"{sym} 12m return {ret_12m_record:+.2%} > cash {cash_return:+.2%}")
        else:
            failed.append(f"{sym} 12m return {ret_12m_record:+.2%} <= cash {cash_return:+.2%}")

        if sym in winners:
            action = "ENTRY"
            rationale_tail = f"top-{max_holdings} risk asset, all filters passed"
        else:
            action = "EXIT"
            rationale_tail = "; ".join(failed) if failed else "outranked by another asset"

        signals.append(Signal(
            symbol=sym, action=action, strategy=name,
            confidence_inputs={**inputs_summary, "this_symbol_ret_12m": ret_12m_record},
            confirmations_passed=passed, confirmations_failed=failed,
            rationale=f"{name}: {action} — {rationale_tail}",
        ))

    # Cash floor signal: ENTRY into SHV iff no risk asset qualifies.
    cash_action = "ENTRY" if not winners else "EXIT"
    signals.append(Signal(
        symbol=TAA_CASH_PROXY, action=cash_action, strategy=name,
        confidence_inputs=inputs_summary,
        confirmations_passed=["No risk asset clears momentum + MA filters"] if cash_action == "ENTRY" else [],
        confirmations_failed=[] if cash_action == "ENTRY" else ["A risk asset is qualifying; cash exit"],
        rationale=f"{name}: {cash_action} — {'cash floor active' if cash_action == 'ENTRY' else 'risk asset qualifying'}",
    ))
    return signals


# ---------------------------------------------------------------------------
# Strategy B: large_cap_momentum_top5
# ---------------------------------------------------------------------------

def evaluate_large_cap_momentum_top5(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
    params: dict | None = None,
) -> list[Signal]:
    """Top-N momentum on a curated large-cap universe.

    Rule book:
      1. For each large-cap symbol in `watchlist_symbols` tagged as `momentum_universe`:
         compute `momentum_window`-day total return.
      2. Apply a market-trend filter: SPY must be above its 10-month MA
         (avoids the worst of bear-market momentum crashes).
      3. Hold the top-N by return (default 5), equally weighted.
      4. Exit any held name that falls out of top-N+2 (buffer to avoid whipsaw).
      5. Per-position stop loss handled by the routine layer via decision invalidation,
         not by signals.py — signals are positional, stops are tactical.

    Optional params:
      momentum_window_days: int = 126      # ~6 months
      ma_window_days: int = 210            # ~10 months SPY trend filter
      top_n_entry: int = 5
      top_n_exit: int = 7                  # buffer to reduce churn
    """
    p = params or {}
    momentum_window = int(p.get("momentum_window_days", 126))
    ma_window = int(p.get("ma_window_days", 210))
    top_n_entry = int(p.get("top_n_entry", 5))
    top_n_exit = int(p.get("top_n_exit", 7))
    assert top_n_exit >= top_n_entry

    name = "large_cap_momentum_top5"
    if "SPY" not in bars_by_symbol:
        return []
    spy_closes = indicators.closes(bars_by_symbol["SPY"])
    if len(spy_closes) < ma_window + 1:
        return []

    # Trend filter: only run the strategy when SPY is in a bullish trend.
    spy_above_ma = indicators.above_sma(spy_closes, ma_window) or False

    # Identify the "momentum universe" — large-caps in watchlist excluding the macro ETFs.
    macro_etfs = set(TAA_RISK_ASSETS + [TAA_CASH_PROXY])
    universe = [s for s in watchlist_symbols
                if s not in macro_etfs and s in bars_by_symbol and s != "SPY"]
    if not universe:
        return []

    returns: dict[str, float] = {}
    for sym in universe:
        c = indicators.closes(bars_by_symbol[sym])
        if len(c) < momentum_window + 1:
            continue
        returns[sym] = (c[-1] / c[-momentum_window - 1]) - 1.0

    if not returns:
        return []

    ranked = sorted(returns.items(), key=lambda x: x[1], reverse=True)
    top_entry = {s for s, _ in ranked[:top_n_entry]}
    top_exit = {s for s, _ in ranked[:top_n_exit]}

    signals: list[Signal] = []
    for sym in universe:
        ret = returns.get(sym)
        passed: list[str] = []
        failed: list[str] = []

        if spy_above_ma:
            passed.append("SPY trend filter passed (above 10m MA)")
        else:
            failed.append(f"SPY trend filter failed (SPY below {ma_window}d MA)")

        in_top_entry = sym in top_entry
        in_top_exit = sym in top_exit

        if ret is None:
            failed.append("insufficient bars for momentum")
        elif in_top_entry:
            passed.append(f"{sym} in top-{top_n_entry} by {momentum_window}d return ({ret:+.2%})")
        else:
            failed.append(f"{sym} not in top-{top_n_entry} (rank by ret)")

        # ENTRY only when SPY trend is up AND symbol is in top-N.
        if spy_above_ma and in_top_entry:
            action = "ENTRY"
            rationale_tail = f"in top-{top_n_entry}, SPY trend up"
        elif (not spy_above_ma) or (not in_top_exit):
            # EXIT when SPY trend turns down OR symbol drops below top-N+2 buffer.
            action = "EXIT"
            rationale_tail = "trend filter broke OR fell out of top-N+2 buffer"
        else:
            # NO_SIGNAL = hold zone (rank N+1 to N+2 while SPY trend up).
            action = "NO_SIGNAL"
            rationale_tail = "hold zone (rank within buffer)"

        signals.append(Signal(
            symbol=sym, action=action, strategy=name,
            confidence_inputs={
                "spy_above_ma": spy_above_ma,
                "return_6m": ret,
                "rank": next((i + 1 for i, (s, _) in enumerate(ranked) if s == sym), None),
                "universe_size": len(universe),
            },
            confirmations_passed=passed,
            confirmations_failed=failed,
            rationale=f"{name}: {action} — {rationale_tail}",
        ))
    return signals


# ---------------------------------------------------------------------------
# Strategy C: gold_permanent_overlay
# ---------------------------------------------------------------------------

def evaluate_gold_permanent_overlay(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
    params: dict | None = None,
) -> list[Signal]:
    """Permanent GLD allocation. Always ENTRY on GLD (the allocator handles sizing).

    This isn't really a "signal" strategy — it's a permanent allocation policy.
    Modeled as a strategy for consistency with the rest of the system: it always
    emits ENTRY on GLD, and the backtest/portfolio combiner gives it 10% of capital.
    """
    name = "gold_permanent_overlay"
    if "GLD" not in bars_by_symbol:
        return []
    return [Signal(
        symbol="GLD", action="ENTRY", strategy=name,
        confidence_inputs={},
        confirmations_passed=["Permanent allocation policy"],
        confirmations_failed=[],
        rationale=f"{name}: ENTRY — permanent 10% GLD allocation",
    )]


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

STRATEGY_FUNCS = {
    "dual_momentum_taa": evaluate_dual_momentum_taa,
    "large_cap_momentum_top5": evaluate_large_cap_momentum_top5,
    "gold_permanent_overlay": evaluate_gold_permanent_overlay,
}


def evaluate_all(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
    strategy_params: dict[str, dict] | None = None,
) -> list[Signal]:
    """Run every ACTIVE_PAPER_TEST strategy and return all signals.

    Multi-strategy portfolio note: the signals from different strategies may
    target the same symbol (e.g., SPY can be held by `dual_momentum_taa`). The
    backtest portfolio combiner and the routine layer are responsible for
    allocating capital per strategy — signals.py just emits per-strategy
    intent, not portfolio-level decisions.
    """
    active = {s["name"] for s in strategy_rules.get("allowed_strategies", [])
              if s.get("status") == "ACTIVE_PAPER_TEST"}
    params_map = strategy_params or {}

    out: list[Signal] = []
    for name, fn in STRATEGY_FUNCS.items():
        if name not in active:
            continue
        out.extend(fn(bars_by_symbol, watchlist_symbols, regime, strategy_rules,
                      params=params_map.get(name)))
    return out
