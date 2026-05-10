"""Deterministic strategy signal generation.

This module is the **decision-making core** of Calm Turtle. The LLM does not decide
trades — Python does, based on `config/strategy_rules.yaml > required_confirmations`.
The LLM's role is to wrap each signal with context (regime relevance, news interaction,
invalidation explanation, risk/reward) and gate via Risk Manager + Compliance.

Public entry point: `evaluate_all(bars_by_symbol, watchlist, strategy_rules)` returns
a list of `Signal` objects, one per (symbol, strategy) where a confirmation set passed.

Every Signal is fully reproducible from the same bar data — that's the whole point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from lib import indicators

# Sector-correlation buckets used in regime defensive tilt.
TECH_CORRELATED = {"XLK", "XLY", "XLC"}
DEFENSIVE_CORRELATED = {"XLP", "XLU", "XLV"}


@dataclass
class Signal:
    """Deterministic signal produced from bar data + strategy rules."""

    symbol: str
    action: str  # ENTRY | HOLD | EXIT | NO_SIGNAL
    strategy: str
    confidence_inputs: dict[str, Any]  # raw indicator readings the rule used
    confirmations_passed: list[str]
    confirmations_failed: list[str]
    rationale: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class RegimeReading:
    """Output of `detect_regime` — deterministic from inputs."""

    regime: str
    confidence: str  # low | medium | high
    indicators: dict[str, Any]
    counter_evidence: list[str]


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def detect_regime(spy_bars: list[dict], vix_value: float | None,
                  sector_rs: dict[str, float] | None = None) -> RegimeReading:
    """Classify the current market regime from bar data + VIX + sector dispersion.

    Rule book (deterministic):
      - high_vol         if VIX > 22.
      - bullish_trend    if SPY > 50DMA AND SPY > 200DMA AND VIX < 18.
      - bearish_trend    if SPY < 50DMA AND SPY < 200DMA.
      - range_bound      if neither bullish nor bearish criteria hold AND VIX in [13, 22].
      - liquidity_stress if VIX > 30 (overrides high_vol).
      - uncertain        otherwise.
    """
    closes = indicators.closes(spy_bars)
    spy_above_50 = indicators.above_sma(closes, 50)
    spy_above_200 = indicators.above_sma(closes, 200)
    spy_pct_50 = indicators.pct_from_sma(closes, 50)

    inds: dict[str, Any] = {
        "spy_above_50dma": spy_above_50,
        "spy_above_200dma": spy_above_200,
        "spy_pct_from_50dma": spy_pct_50,
        "vix": vix_value,
    }

    if vix_value is not None and vix_value > 30:
        return RegimeReading("liquidity_stress", "high", inds,
                             counter_evidence=["VIX could spike-and-revert; not all >30 are stress"])
    if vix_value is not None and vix_value > 22:
        return RegimeReading("high_vol", "medium", inds,
                             counter_evidence=["High VIX without breadth deterioration may be transient"])
    if spy_above_50 and spy_above_200 and vix_value is not None and vix_value < 18:
        return RegimeReading("bullish_trend", "medium", inds,
                             counter_evidence=["Trend can break on macro shocks; not a guarantee"])
    if spy_above_50 is False and spy_above_200 is False:
        return RegimeReading("bearish_trend", "medium", inds,
                             counter_evidence=["A bounce off 200DMA is possible"])
    if (spy_above_50 is not None
        and vix_value is not None and 13 <= vix_value <= 22):
        return RegimeReading("range_bound", "low", inds,
                             counter_evidence=["Could break out either direction"])
    return RegimeReading("uncertain", "low", inds, counter_evidence=["Insufficient signal coherence"])


# ---------------------------------------------------------------------------
# Strategy: sector_relative_strength_rotation
# ---------------------------------------------------------------------------

def evaluate_sector_relative_strength_rotation(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
) -> list[Signal]:
    """Deterministic implementation of the sector RS rotation strategy.

    Confirmations from strategy_rules.yaml:
      1. Up-regime confirmed (SPY > 50DMA AND breadth positive)
      2. Sector RS rank top-3 vs SPY on both 20d AND 60d windows
      3. Sector ETF above its own 50DMA
    """
    name = "sector_relative_strength_rotation"
    if "SPY" not in bars_by_symbol:
        return []

    spy_closes = indicators.closes(bars_by_symbol["SPY"])
    sector_symbols = [s for s in watchlist_symbols if s != "SPY" and s in bars_by_symbol]

    # Compute RS on both windows.
    rs_20d: dict[str, float] = {}
    rs_60d: dict[str, float] = {}
    for sym in sector_symbols:
        closes = indicators.closes(bars_by_symbol[sym])
        r20 = indicators.relative_strength(closes, spy_closes, 20)
        r60 = indicators.relative_strength(closes, spy_closes, 60)
        if r20 is not None:
            rs_20d[sym] = r20
        if r60 is not None:
            rs_60d[sym] = r60

    top3_20d = {s for s, _ in sorted(rs_20d.items(), key=lambda x: x[1], reverse=True)[:3]}
    top3_60d = {s for s, _ in sorted(rs_60d.items(), key=lambda x: x[1], reverse=True)[:3]}

    signals: list[Signal] = []
    for sym in sector_symbols:
        sym_closes = indicators.closes(bars_by_symbol[sym])
        passed: list[str] = []
        failed: list[str] = []

        # Confirmation 1: up-regime.
        if regime.regime == "bullish_trend":
            passed.append("Up-regime confirmed (SPY > 50DMA AND breadth positive)")
        else:
            failed.append(f"Up-regime not confirmed (regime={regime.regime})")

        # Confirmation 2: top-3 RS on both windows.
        if sym in top3_20d and sym in top3_60d:
            passed.append("Sector RS rank top-3 vs SPY on both 20d AND 60d windows")
        else:
            failed.append(f"Not top-3 RS on both windows (20d in top3={sym in top3_20d}, 60d in top3={sym in top3_60d})")

        # Confirmation 3: ETF above its own 50DMA.
        above_50 = indicators.above_sma(sym_closes, 50)
        if above_50:
            passed.append("Sector ETF above its own 50DMA")
        else:
            failed.append(f"ETF not above 50DMA (above_50dma={above_50})")

        action = "ENTRY" if not failed else "NO_SIGNAL"
        signals.append(Signal(
            symbol=sym,
            action=action,
            strategy=name,
            confidence_inputs={
                "rs_20d": rs_20d.get(sym),
                "rs_60d": rs_60d.get(sym),
                "rs_20d_rank_top3": sym in top3_20d,
                "rs_60d_rank_top3": sym in top3_60d,
                "above_50dma": above_50,
                "regime": regime.regime,
            },
            confirmations_passed=passed,
            confirmations_failed=failed,
            rationale=(
                f"{name}: " + ("ENTRY — all confirmations passed" if action == "ENTRY"
                                else f"NO_SIGNAL — failed: {'; '.join(failed)}")
            ),
        ))
    return signals


# ---------------------------------------------------------------------------
# Strategy: regime_defensive_tilt
# ---------------------------------------------------------------------------

def evaluate_regime_defensive_tilt(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
) -> list[Signal]:
    """Deterministic implementation of the defensive-tilt strategy.

    Fires when regime is high_vol or breadth deterioration is detected, suggesting
    rotation TOWARD XLP/XLU/XLV and AWAY FROM XLK/XLY/XLC.
    """
    name = "regime_defensive_tilt"
    if "SPY" not in bars_by_symbol:
        return []

    spy_closes = indicators.closes(bars_by_symbol["SPY"])
    spy_below_50 = indicators.above_sma(spy_closes, 50) is False
    is_risk_off = (
        regime.regime in {"high_vol", "liquidity_stress", "bearish_trend"}
        or (regime.indicators.get("vix") or 0) > 22
        or spy_below_50
    )

    signals: list[Signal] = []
    for sym in DEFENSIVE_CORRELATED:
        if sym not in bars_by_symbol:
            continue
        closes = indicators.closes(bars_by_symbol[sym])
        rs_10d = indicators.relative_strength(closes, spy_closes, 10)

        passed: list[str] = []
        failed: list[str] = []
        if is_risk_off:
            passed.append("VIX > 22 OR SPY < 50DMA OR sector breadth turning negative")
        else:
            failed.append("Not risk-off; no defensive tilt warranted")
        if rs_10d is not None and rs_10d > 0:
            passed.append(f"Defensive sector RS improving vs SPY over 10d (rs_10d={rs_10d:+.4f})")
        else:
            failed.append(f"Defensive sector RS not improving (rs_10d={rs_10d})")

        action = "ENTRY" if not failed and sym in watchlist_symbols else "NO_SIGNAL"
        signals.append(Signal(
            symbol=sym,
            action=action,
            strategy=name,
            confidence_inputs={"rs_10d": rs_10d, "is_risk_off": is_risk_off, "regime": regime.regime},
            confirmations_passed=passed,
            confirmations_failed=failed,
            rationale=(f"{name}: " + ("ENTRY — defensive tilt confirmed" if action == "ENTRY"
                                       else f"NO_SIGNAL — failed: {'; '.join(failed)}")),
        ))

    # Also emit EXIT signals on tech-correlated names if risk-off.
    if is_risk_off:
        for sym in TECH_CORRELATED & set(watchlist_symbols):
            signals.append(Signal(
                symbol=sym,
                action="EXIT" if sym in bars_by_symbol else "NO_SIGNAL",
                strategy=name,
                confidence_inputs={"is_risk_off": True, "regime": regime.regime},
                confirmations_passed=["Risk-off regime — exit tech-correlated exposure"],
                confirmations_failed=[],
                rationale=f"{name}: EXIT — defensive tilt away from tech-correlated names",
            ))
    return signals


# ---------------------------------------------------------------------------
# Strategy: trend_pullback_in_leader
# ---------------------------------------------------------------------------

def evaluate_trend_pullback_in_leader(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
) -> list[Signal]:
    """Pullback to 20DMA on a top-3 RS sector with RSI in 40-55 (mild pullback).

    This strategy is `NEEDS_MORE_DATA` until proven; signals.py emits them anyway so
    they appear in backtests. Routine prompts decide whether to act based on status.
    """
    name = "trend_pullback_in_leader"
    if "SPY" not in bars_by_symbol or regime.regime != "bullish_trend":
        return []

    spy_closes = indicators.closes(bars_by_symbol["SPY"])
    sector_symbols = [s for s in watchlist_symbols if s != "SPY" and s in bars_by_symbol]

    rs_20d: dict[str, float] = {}
    for sym in sector_symbols:
        c = indicators.closes(bars_by_symbol[sym])
        r = indicators.relative_strength(c, spy_closes, 20)
        if r is not None:
            rs_20d[sym] = r
    top3_20d = {s for s, _ in sorted(rs_20d.items(), key=lambda x: x[1], reverse=True)[:3]}

    signals: list[Signal] = []
    for sym in sector_symbols:
        c = indicators.closes(bars_by_symbol[sym])
        pct_from_20 = indicators.pct_from_sma(c, 20)
        rsi_val = indicators.rsi(c, 14)

        passed: list[str] = []
        failed: list[str] = []
        if sym in top3_20d:
            passed.append("ETF in top-3 sector RS")
        else:
            failed.append("Not in top-3 RS")
        if pct_from_20 is not None and -0.03 <= pct_from_20 <= -0.005:
            passed.append(f"Pullback within 2-3% of 20DMA (pct_from_20={pct_from_20:+.4f})")
        else:
            failed.append(f"Not within 2-3% pullback (pct_from_20={pct_from_20})")
        if rsi_val is not None and 40 <= rsi_val <= 55:
            passed.append(f"RSI between 40-55 (rsi={rsi_val:.1f})")
        else:
            failed.append(f"RSI outside 40-55 (rsi={rsi_val})")

        action = "ENTRY" if not failed else "NO_SIGNAL"
        signals.append(Signal(
            symbol=sym,
            action=action,
            strategy=name,
            confidence_inputs={"rs_20d": rs_20d.get(sym), "pct_from_20dma": pct_from_20, "rsi": rsi_val},
            confirmations_passed=passed,
            confirmations_failed=failed,
            rationale=(f"{name}: " + ("ENTRY — pullback in leader" if action == "ENTRY"
                                       else f"NO_SIGNAL — failed: {'; '.join(failed)}")),
        ))
    return signals


# ---------------------------------------------------------------------------
# Strategy: spy_neutral_default
# ---------------------------------------------------------------------------

def evaluate_spy_neutral_default(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    other_signals: list[Signal],
    strategy_rules: dict,
) -> list[Signal]:
    """Hold SPY when no other strategy fires an ENTRY. The do-no-harm default."""
    name = "spy_neutral_default"
    any_entry = any(s.action == "ENTRY" for s in other_signals)
    if any_entry:
        return [Signal(
            symbol="SPY",
            action="NO_SIGNAL",
            strategy=name,
            confidence_inputs={"any_other_entry": True},
            confirmations_passed=[],
            confirmations_failed=["Other strategy fired an entry; default not applicable"],
            rationale=f"{name}: NO_SIGNAL — another strategy is active",
        )]
    return [Signal(
        symbol="SPY",
        action="ENTRY",
        strategy=name,
        confidence_inputs={"any_other_entry": False},
        confirmations_passed=["No sector ETF passes any of the above criteria"],
        confirmations_failed=[],
        rationale=f"{name}: ENTRY — neutral default (hold SPY)",
    )]


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

STRATEGY_FUNCS = {
    "sector_relative_strength_rotation": evaluate_sector_relative_strength_rotation,
    "regime_defensive_tilt": evaluate_regime_defensive_tilt,
    "trend_pullback_in_leader": evaluate_trend_pullback_in_leader,
    # spy_neutral_default is special-cased below — it depends on the others.
}


def evaluate_all(
    bars_by_symbol: dict[str, list[dict]],
    watchlist_symbols: list[str],
    regime: RegimeReading,
    strategy_rules: dict,
) -> list[Signal]:
    """Run every ACTIVE_PAPER_TEST strategy and return all signals.

    Skips strategies whose status is NEEDS_MORE_DATA (signals are still computed for
    backtesting via `evaluate_strategy(...)` directly, but routines should not act on
    NEEDS_MORE_DATA signals — they're for analysis only).
    """
    active = {s["name"] for s in strategy_rules.get("allowed_strategies", [])
              if s.get("status") == "ACTIVE_PAPER_TEST"}

    out: list[Signal] = []
    for name, fn in STRATEGY_FUNCS.items():
        if name not in active:
            continue
        out.extend(fn(bars_by_symbol, watchlist_symbols, regime, strategy_rules))

    if "spy_neutral_default" in active:
        out.extend(evaluate_spy_neutral_default(
            bars_by_symbol, watchlist_symbols, regime, out, strategy_rules
        ))
    return out
