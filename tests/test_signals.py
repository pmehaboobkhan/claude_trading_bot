"""Unit tests for lib/signals.py and lib/indicators.py — post-pivot strategy set.

Strategies tested:
  - dual_momentum_taa
  - large_cap_momentum_top5
  - gold_permanent_overlay

Run with: pytest tests/test_signals.py -v
"""
from __future__ import annotations

import pytest

from lib import indicators, signals


def _trend_bars(n: int, start: float = 100.0, daily_pct: float = 0.001) -> list[dict]:
    bars = []
    for i in range(n):
        close = start * (1 + daily_pct) ** i
        bars.append({
            "ts": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
            "open": close * 0.999, "high": close * 1.001,
            "low": close * 0.998, "close": close, "volume": 1_000_000,
        })
    return bars


def _flat_bars(n: int, price: float = 100.0) -> list[dict]:
    return [{
        "ts": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
        "open": price, "high": price, "low": price, "close": price, "volume": 1_000_000,
    } for i in range(n)]


# ---------------------------------------------------------------------------
# Indicator tests (unchanged from prior version)
# ---------------------------------------------------------------------------

def test_sma_simple() -> None:
    assert indicators.sma([1, 2, 3, 4, 5], 5) == 3.0
    assert indicators.sma([1, 2, 3, 4, 5], 3) == 4.0
    assert indicators.sma([1, 2], 3) is None


def test_rsi_flat_returns_neutral() -> None:
    rsi = indicators.rsi([100.0] * 20, period=14)
    assert rsi == 100.0


def test_rsi_strong_uptrend_above_70() -> None:
    closes = [float(i) for i in range(100, 130)]
    rsi = indicators.rsi(closes, period=14)
    assert rsi is not None and rsi > 70


def test_atr_uniform_bars() -> None:
    bars = _flat_bars(30, price=100)
    assert indicators.atr(bars, period=14) == 0.0


def test_relative_strength_positive_when_outperforming() -> None:
    target = [float(i) for i in range(100, 122)]
    bench = [float(i) for i in range(100, 111)] + [110.0] * 11
    rs = indicators.relative_strength(target, bench, window=20)
    assert rs is not None and rs > 0


# ---------------------------------------------------------------------------
# Regime detection (works without VIX)
# ---------------------------------------------------------------------------

def test_detect_regime_bullish_with_vix() -> None:
    bars = _trend_bars(250, start=100, daily_pct=0.002)
    r = signals.detect_regime(bars, vix_value=14)
    assert r.regime == "bullish_trend"


def test_detect_regime_high_vol() -> None:
    bars = _trend_bars(250)
    r = signals.detect_regime(bars, vix_value=25)
    assert r.regime == "high_vol"


def test_detect_regime_liquidity_stress_overrides() -> None:
    bars = _trend_bars(250)
    r = signals.detect_regime(bars, vix_value=35)
    assert r.regime == "liquidity_stress"


# ---------------------------------------------------------------------------
# Strategy A: dual_momentum_taa
# ---------------------------------------------------------------------------

def test_taa_holds_strongest_risk_asset() -> None:
    """When SPY trends up strongly and others lag, TAA should ENTRY SPY, EXIT others."""
    bars = {
        "SPY": _trend_bars(280, start=400, daily_pct=0.0015),    # strong uptrend
        "IEF": _trend_bars(280, start=100, daily_pct=0.0002),    # weak uptrend
        "GLD": _trend_bars(280, start=180, daily_pct=0.0001),    # nearly flat
        "SHV": _trend_bars(280, start=110, daily_pct=0.00015),   # cash floor
    }
    sigs = signals.evaluate_dual_momentum_taa(
        bars, watchlist_symbols=list(bars.keys()),
        regime=signals.RegimeReading("bullish_trend", "medium", {}, []),
        strategy_rules={},
    )
    spy_sigs = [s for s in sigs if s.symbol == "SPY"]
    ief_sigs = [s for s in sigs if s.symbol == "IEF"]
    shv_sigs = [s for s in sigs if s.symbol == "SHV"]
    assert any(s.action == "ENTRY" for s in spy_sigs), "SPY should be the chosen risk asset"
    assert any(s.action == "EXIT" for s in ief_sigs), "IEF should exit (outranked)"
    assert any(s.action == "EXIT" for s in shv_sigs), "SHV should exit (risk asset qualifying)"


def test_taa_falls_to_cash_when_no_risk_asset_qualifies() -> None:
    """When all risk assets are below their 10-month MA, hold cash (SHV)."""
    bars = {
        "SPY": _trend_bars(280, start=400, daily_pct=-0.0015),   # strong DOWNtrend
        "IEF": _trend_bars(280, start=100, daily_pct=-0.0005),
        "GLD": _trend_bars(280, start=180, daily_pct=-0.0008),
        "SHV": _trend_bars(280, start=110, daily_pct=0.0002),    # cash always positive
    }
    sigs = signals.evaluate_dual_momentum_taa(
        bars, watchlist_symbols=list(bars.keys()),
        regime=signals.RegimeReading("bearish_trend", "medium", {}, []),
        strategy_rules={},
    )
    shv_sigs = [s for s in sigs if s.symbol == "SHV"]
    assert any(s.action == "ENTRY" for s in shv_sigs), "Cash floor should activate"
    for sym in ("SPY", "IEF", "GLD"):
        sym_sigs = [s for s in sigs if s.symbol == sym]
        assert all(s.action != "ENTRY" for s in sym_sigs), f"{sym} should not enter in bear regime"


def test_taa_returns_empty_when_required_symbols_missing() -> None:
    """If SHV is missing, can't compute cash floor — return no signals."""
    bars = {"SPY": _trend_bars(280), "IEF": _trend_bars(280), "GLD": _trend_bars(280)}
    sigs = signals.evaluate_dual_momentum_taa(
        bars, watchlist_symbols=list(bars.keys()),
        regime=signals.RegimeReading("bullish_trend", "medium", {}, []),
        strategy_rules={},
    )
    assert sigs == []


# ---------------------------------------------------------------------------
# Strategy B: large_cap_momentum_top5
# ---------------------------------------------------------------------------

def test_large_cap_momentum_picks_top5_in_bullish_trend() -> None:
    """When SPY is in uptrend, top-5 momentum stocks should ENTRY."""
    bars = {
        "SPY": _trend_bars(280, start=400, daily_pct=0.0015),
        "IEF": _trend_bars(280, start=100, daily_pct=0.0005),
        "GLD": _trend_bars(280, start=180, daily_pct=0.0003),
        "SHV": _trend_bars(280, start=110, daily_pct=0.0002),
        # 7 candidate stocks with varying momentum:
        "STOCK_A": _trend_bars(280, start=100, daily_pct=0.0030),   # rank 1
        "STOCK_B": _trend_bars(280, start=100, daily_pct=0.0025),   # rank 2
        "STOCK_C": _trend_bars(280, start=100, daily_pct=0.0020),   # rank 3
        "STOCK_D": _trend_bars(280, start=100, daily_pct=0.0015),   # rank 4
        "STOCK_E": _trend_bars(280, start=100, daily_pct=0.0010),   # rank 5
        "STOCK_F": _trend_bars(280, start=100, daily_pct=0.0005),   # rank 6
        "STOCK_G": _trend_bars(280, start=100, daily_pct=0.0000),   # rank 7
    }
    sigs = signals.evaluate_large_cap_momentum_top5(
        bars, watchlist_symbols=list(bars.keys()),
        regime=signals.RegimeReading("bullish_trend", "medium", {}, []),
        strategy_rules={},
    )
    entries = {s.symbol for s in sigs if s.action == "ENTRY"}
    assert entries == {"STOCK_A", "STOCK_B", "STOCK_C", "STOCK_D", "STOCK_E"}, \
        f"Expected top-5, got {entries}"


def test_large_cap_momentum_filters_via_spy_trend() -> None:
    """When SPY is below 10-month MA, no entries even if stocks have momentum."""
    bars = {
        "SPY": _trend_bars(280, start=400, daily_pct=-0.0015),   # SPY in downtrend
        "STOCK_A": _trend_bars(280, start=100, daily_pct=0.0030),
        "STOCK_B": _trend_bars(280, start=100, daily_pct=0.0025),
    }
    sigs = signals.evaluate_large_cap_momentum_top5(
        bars, watchlist_symbols=list(bars.keys()),
        regime=signals.RegimeReading("bearish_trend", "medium", {}, []),
        strategy_rules={},
    )
    entries = [s for s in sigs if s.action == "ENTRY"]
    assert entries == [], "No entries when SPY trend is down"
    exits = [s for s in sigs if s.action == "EXIT"]
    assert len(exits) == 2, "Both stocks should EXIT under trend filter"


# ---------------------------------------------------------------------------
# Strategy C: gold_permanent_overlay
# ---------------------------------------------------------------------------

def test_gold_overlay_always_enters_gld() -> None:
    bars = {"GLD": _trend_bars(50)}
    sigs = signals.evaluate_gold_permanent_overlay(
        bars, watchlist_symbols=["GLD"],
        regime=signals.RegimeReading("uncertain", "low", {}, []),
        strategy_rules={},
    )
    assert len(sigs) == 1
    assert sigs[0].symbol == "GLD"
    assert sigs[0].action == "ENTRY"


def test_gold_overlay_returns_empty_when_gld_missing() -> None:
    sigs = signals.evaluate_gold_permanent_overlay(
        {}, watchlist_symbols=[],
        regime=signals.RegimeReading("uncertain", "low", {}, []),
        strategy_rules={},
    )
    assert sigs == []


# ---------------------------------------------------------------------------
# evaluate_all integration
# ---------------------------------------------------------------------------

def test_evaluate_all_runs_only_active_strategies() -> None:
    bars = {
        "SPY": _trend_bars(280, start=400, daily_pct=0.0015),
        "IEF": _trend_bars(280, start=100, daily_pct=0.0005),
        "GLD": _trend_bars(280, start=180, daily_pct=0.0008),
        "SHV": _trend_bars(280, start=110, daily_pct=0.0002),
    }
    rules_only_taa_active = {
        "allowed_strategies": [
            {"name": "dual_momentum_taa", "status": "ACTIVE_PAPER_TEST", "description": ""},
            {"name": "large_cap_momentum_top5", "status": "NEEDS_MORE_DATA", "description": ""},
            {"name": "gold_permanent_overlay", "status": "NEEDS_MORE_DATA", "description": ""},
        ],
    }
    regime = signals.detect_regime(bars["SPY"], vix_value=14)
    sigs = signals.evaluate_all(bars, list(bars.keys()), regime, rules_only_taa_active)
    strategies_seen = {s.strategy for s in sigs}
    assert strategies_seen == {"dual_momentum_taa"}, \
        "Only ACTIVE strategies should emit signals"


def test_signals_are_reproducible() -> None:
    """Same inputs → same outputs. Core property of deterministic decisions."""
    bars = {
        "SPY": _trend_bars(280, start=400, daily_pct=0.0015),
        "IEF": _trend_bars(280, start=100, daily_pct=0.0005),
        "GLD": _trend_bars(280, start=180, daily_pct=0.0003),
        "SHV": _trend_bars(280, start=110, daily_pct=0.0002),
    }
    rules = {"allowed_strategies": [
        {"name": "dual_momentum_taa", "status": "ACTIVE_PAPER_TEST", "description": ""},
    ]}
    regime = signals.detect_regime(bars["SPY"], vix_value=14)
    a = signals.evaluate_all(bars, list(bars.keys()), regime, rules)
    b = signals.evaluate_all(bars, list(bars.keys()), regime, rules)
    a_facts = [(s.symbol, s.action, s.strategy, tuple(s.confirmations_passed)) for s in a]
    b_facts = [(s.symbol, s.action, s.strategy, tuple(s.confirmations_passed)) for s in b]
    assert a_facts == b_facts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
