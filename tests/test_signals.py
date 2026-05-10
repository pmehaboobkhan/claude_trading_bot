"""Unit tests for lib/signals.py and lib/indicators.py.

These tests are deterministic — they don't hit the network or the LLM. They prove
that the decision logic is reproducible from input bars alone.

Run with: pytest tests/test_signals.py -v
"""
from __future__ import annotations

import pytest

from lib import indicators, signals


def _trend_bars(n: int, start: float = 100.0, daily_pct: float = 0.001) -> list[dict]:
    """Construct n daily bars with a steady uptrend at `daily_pct` per day."""
    bars = []
    price = start
    for i in range(n):
        close = price * (1 + daily_pct) ** i
        bars.append({"ts": f"2025-01-{i+1:02d}T00:00:00Z",
                     "open": close * 0.999, "high": close * 1.001,
                     "low": close * 0.998, "close": close, "volume": 1_000_000})
    return bars


def _flat_bars(n: int, price: float = 100.0) -> list[dict]:
    return [{"ts": f"2025-01-{i+1:02d}T00:00:00Z",
             "open": price, "high": price, "low": price,
             "close": price, "volume": 1_000_000} for i in range(n)]


def test_sma_simple() -> None:
    assert indicators.sma([1, 2, 3, 4, 5], 5) == 3.0
    assert indicators.sma([1, 2, 3, 4, 5], 3) == 4.0
    assert indicators.sma([1, 2], 3) is None


def test_rsi_flat_returns_neutral() -> None:
    # Pure flat data has zero gains and zero losses → RSI is undefined; our impl returns 100.
    rsi = indicators.rsi([100.0] * 20, period=14)
    assert rsi == 100.0


def test_rsi_strong_uptrend_above_70() -> None:
    closes = [float(i) for i in range(100, 130)]  # strictly increasing
    rsi = indicators.rsi(closes, period=14)
    assert rsi is not None and rsi > 70


def test_atr_uniform_bars() -> None:
    bars = _flat_bars(30, price=100)
    # Flat bars have zero true range.
    assert indicators.atr(bars, period=14) == 0.0


def test_relative_strength_positive_when_outperforming() -> None:
    target = [float(i) for i in range(100, 122)]   # +21%
    bench = [float(i) for i in range(100, 111)] + [110.0] * 11  # +10% then flat
    rs = indicators.relative_strength(target, bench, window=20)
    assert rs is not None and rs > 0


def test_detect_regime_bullish_requires_low_vix() -> None:
    bars = _trend_bars(250, start=100, daily_pct=0.002)
    r = signals.detect_regime(bars, vix_value=14)
    assert r.regime == "bullish_trend"
    assert r.confidence == "medium"


def test_detect_regime_high_vol() -> None:
    bars = _trend_bars(250)
    r = signals.detect_regime(bars, vix_value=25)
    assert r.regime == "high_vol"


def test_detect_regime_liquidity_stress_overrides() -> None:
    bars = _trend_bars(250)
    r = signals.detect_regime(bars, vix_value=35)
    assert r.regime == "liquidity_stress"


def test_signals_evaluate_all_returns_signals_only_for_active_strategies() -> None:
    bars = {
        "SPY": _trend_bars(250, start=400, daily_pct=0.002),
        "XLK": _trend_bars(250, start=200, daily_pct=0.003),  # outperforms SPY
        "XLF": _trend_bars(250, start=40, daily_pct=0.0005),  # underperforms
        "XLE": _trend_bars(250, start=80, daily_pct=0.001),
        "XLV": _trend_bars(250, start=140, daily_pct=0.0008),
        "XLY": _trend_bars(250, start=190, daily_pct=0.0015),
        "XLP": _trend_bars(250, start=75, daily_pct=0.0007),
        "XLI": _trend_bars(250, start=120, daily_pct=0.0012),
        "XLB": _trend_bars(250, start=85, daily_pct=0.0009),
        "XLRE": _trend_bars(250, start=42, daily_pct=0.0008),
        "XLU": _trend_bars(250, start=70, daily_pct=0.0006),
        "XLC": _trend_bars(250, start=80, daily_pct=0.0014),
    }
    symbols = list(bars.keys())
    regime = signals.detect_regime(bars["SPY"], vix_value=14)
    rules = {
        "allowed_strategies": [
            {"name": "sector_relative_strength_rotation", "status": "ACTIVE_PAPER_TEST",
             "description": ""},
            {"name": "spy_neutral_default", "status": "ACTIVE_PAPER_TEST",
             "description": ""},
            {"name": "trend_pullback_in_leader", "status": "NEEDS_MORE_DATA",
             "description": ""},
        ],
    }
    sigs = signals.evaluate_all(bars, symbols, regime, rules)
    strategies_seen = {s.strategy for s in sigs}
    # NEEDS_MORE_DATA strategies are excluded.
    assert "trend_pullback_in_leader" not in strategies_seen
    # Active strategies present.
    assert "sector_relative_strength_rotation" in strategies_seen
    # XLK had the strongest uptrend — should be in top-3 RS and produce an ENTRY.
    xlk_sigs = [s for s in sigs if s.symbol == "XLK"
                and s.strategy == "sector_relative_strength_rotation"]
    assert any(s.action == "ENTRY" for s in xlk_sigs)


def test_signals_are_reproducible() -> None:
    """Same inputs → same outputs. The whole point of moving decisions to Python."""
    bars = {
        "SPY": _trend_bars(250, start=400, daily_pct=0.001),
        "XLK": _trend_bars(250, start=200, daily_pct=0.0015),
        "XLF": _trend_bars(250, start=40, daily_pct=0.0008),
    }
    rules = {
        "allowed_strategies": [
            {"name": "sector_relative_strength_rotation", "status": "ACTIVE_PAPER_TEST",
             "description": ""},
        ],
    }
    regime = signals.detect_regime(bars["SPY"], vix_value=14)
    a = signals.evaluate_all(bars, list(bars.keys()), regime, rules)
    b = signals.evaluate_all(bars, list(bars.keys()), regime, rules)
    # Compare action + confirmations (ignoring timestamps).
    a_facts = [(s.symbol, s.action, tuple(s.confirmations_passed), tuple(s.confirmations_failed)) for s in a]
    b_facts = [(s.symbol, s.action, tuple(s.confirmations_passed), tuple(s.confirmations_failed)) for s in b]
    assert a_facts == b_facts


def test_spy_neutral_default_fires_when_no_other_entry() -> None:
    # Construct bars where regime is bearish so sector RS strategy fires no entries.
    bars = {
        "SPY": _trend_bars(250, start=400, daily_pct=-0.001),  # downtrend
        "XLK": _trend_bars(250, start=200, daily_pct=-0.001),
    }
    rules = {
        "allowed_strategies": [
            {"name": "sector_relative_strength_rotation", "status": "ACTIVE_PAPER_TEST",
             "description": ""},
            {"name": "spy_neutral_default", "status": "ACTIVE_PAPER_TEST",
             "description": ""},
        ],
    }
    regime = signals.detect_regime(bars["SPY"], vix_value=14)
    sigs = signals.evaluate_all(bars, list(bars.keys()), regime, rules)
    spy_sigs = [s for s in sigs if s.symbol == "SPY"]
    assert any(s.action == "ENTRY" and s.strategy == "spy_neutral_default" for s in spy_sigs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
