"""Tests for the MOC signal-proxy validation harness.

The harness measures whether using a ~15:50 price (as a stand-in for today's
close) changes the *decision* vs using the true 16:00 close. These tests pin
the pure comparison core; the heavy lib.signals pipeline is stubbed so the
divergence reducer is tested in isolation (lib.signals has its own suite).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.signals import RegimeReading, Signal  # noqa: E402
from scripts import validate_moc_signal_proxy as vp  # noqa: E402


def _sig(symbol, action, strategy):
    return Signal(
        symbol=symbol, action=action, strategy=strategy,
        confidence_inputs={}, confirmations_passed=[],
        confirmations_failed=[], rationale="",
    )


def _patch_signals(monkeypatch, *, close_sigs, proxy_sigs,
                    regime_close="bullish_trend", regime_proxy="bullish_trend"):
    """Stub detect_regime/evaluate_all to return crafted output keyed by which
    bar history (close vs proxy) is passed in (we tag histories via SPY[-1])."""
    def fake_regime(spy_bars, vix_value, sector_rs=None):
        tag = spy_bars[-1]["close"]
        label = regime_close if tag == 100.0 else regime_proxy
        return RegimeReading(label, "medium", {}, [])

    def fake_eval(bars, syms, regime, rules, strategy_params=None):
        tag = bars["SPY"][-1]["close"]
        return close_sigs if tag == 100.0 else proxy_sigs

    monkeypatch.setattr(vp.signals, "detect_regime", fake_regime)
    monkeypatch.setattr(vp.signals, "evaluate_all", fake_eval)


def _histories():
    # Identical except the SPY last-bar close: 100.0 == "close", 99.0 == "proxy".
    base = [{"ts": f"2026-01-{d:02d}T00:00:00+00:00", "open": 1, "high": 1,
             "low": 1, "close": 1, "volume": 1} for d in range(1, 6)]
    hc = {"SPY": base + [{"ts": "x", "open": 1, "high": 1, "low": 1,
                          "close": 100.0, "volume": 1}]}
    hp = {"SPY": base + [{"ts": "x", "open": 1, "high": 1, "low": 1,
                          "close": 99.0, "volume": 1}]}
    return hc, hp


def test_agreement_when_action_sets_identical(monkeypatch):
    same = [_sig("SPY", "ENTRY", "dual_momentum_taa")]
    _patch_signals(monkeypatch, close_sigs=same, proxy_sigs=list(same))
    hc, hp = _histories()

    out = vp.decision_divergence(hc, hp, ["SPY"], strategy_rules={})

    assert out["agree"] is True
    assert out["divergences"] == []
    assert out["regime_close"] == out["regime_proxy"] == "bullish_trend"


def test_divergence_when_entry_differs(monkeypatch):
    _patch_signals(
        monkeypatch,
        close_sigs=[_sig("AAPL", "ENTRY", "large_cap_momentum_top5")],
        proxy_sigs=[_sig("AAPL", "EXIT", "large_cap_momentum_top5")],
    )
    hc, hp = _histories()

    out = vp.decision_divergence(hc, hp, ["AAPL"], strategy_rules={})

    assert out["agree"] is False
    assert out["divergences"] == [{
        "strategy": "large_cap_momentum_top5", "symbol": "AAPL",
        "close_action": "ENTRY", "proxy_action": "EXIT"}]


def test_build_per_day_iterates_sample_days_with_substituted_proxy(monkeypatch):
    """build_per_day must, for each sample day, run decision_divergence with
    the proxy history = daily history truncated to that day with the last
    close swapped for that day's proxy price, and tag each result with date."""
    daily = {"SPY": [
        {"ts": "2026-05-11T00:00:00+00:00", "open": 1, "high": 1, "low": 1,
         "close": 500.0, "volume": 1},
        {"ts": "2026-05-12T00:00:00+00:00", "open": 1, "high": 1, "low": 1,
         "close": 510.0, "volume": 1},
        {"ts": "2026-05-13T00:00:00+00:00", "open": 1, "high": 1, "low": 1,
         "close": 520.0, "volume": 1},
    ]}
    proxy_by_day = {
        "2026-05-12": {"SPY": 508.0},
        "2026-05-13": {"SPY": 519.0},
    }
    seen = []

    def fake_div(bars_close, bars_proxy, syms, rules, strategy_params=None):
        seen.append((bars_close["SPY"][-1]["close"],
                     bars_proxy["SPY"][-1]["close"],
                     len(bars_close["SPY"])))
        return {"agree": True, "regime_close": "x", "regime_proxy": "x",
                "divergences": [], "close_actions": [], "proxy_actions": []}

    monkeypatch.setattr(vp, "decision_divergence", fake_div)

    out = vp.build_per_day(daily, proxy_by_day, ["SPY"], strategy_rules={})

    assert [d["date"] for d in out] == ["2026-05-12", "2026-05-13"]
    # day 2026-05-12: history truncated to 2 bars, close=510, proxy=508
    assert seen[0] == (510.0, 508.0, 2)
    # day 2026-05-13: history truncated to 3 bars, close=520, proxy=519
    assert seen[1] == (520.0, 519.0, 3)


def _day(date, agree, divs=None, rc="bullish_trend", rp="bullish_trend"):
    return {"date": date, "agree": agree, "divergences": divs or [],
            "regime_close": rc, "regime_proxy": rp}


def test_summarize_all_agree_is_pass():
    days = [_day("2026-05-11", True), _day("2026-05-12", True),
            _day("2026-05-13", True)]
    out = vp.summarize(days, min_agreement_rate=0.99)

    assert out["total_days"] == 3
    assert out["agreement_rate"] == 1.0
    assert out["verdict"] == "PASS"
    assert out["divergent_days"] == []


def test_summarize_below_threshold_is_fail_with_breakdown():
    days = [_day(f"2026-05-{d:02d}", True) for d in range(1, 99)]
    days.append(_day("2026-05-29", False, divs=[
        {"strategy": "large_cap_momentum_top5", "symbol": "AAPL",
         "close_action": "ENTRY", "proxy_action": "NONE"}]))
    days.append(_day("2026-05-30", False, rc="bullish_trend",
                     rp="bearish_trend"))

    out = vp.summarize(days, min_agreement_rate=0.99)

    assert out["total_days"] == 100
    assert out["agreement_rate"] == 0.98
    assert out["verdict"] == "FAIL"
    assert len(out["divergent_days"]) == 2
    assert out["per_strategy_divergences"]["large_cap_momentum_top5"] == 1
    assert out["regime_flip_days"] == 1


def test_summarize_empty_sample_is_fail():
    out = vp.summarize([], min_agreement_rate=0.99)
    assert out["verdict"] == "FAIL"
    assert out["total_days"] == 0
    assert "no sample" in " ".join(out["reasons"]).lower()


def _bar(close, high=None, low=None, open_=10.0):
    return {"ts": "2026-05-15T00:00:00+00:00", "open": open_,
            "high": high if high is not None else max(open_, close),
            "low": low if low is not None else min(open_, close),
            "close": close, "volume": 1000}


def test_substitute_last_close_replaces_only_last_bar():
    bars = [_bar(10.0), _bar(11.0), _bar(12.0)]
    out = vp.substitute_last_close(bars, 11.5)

    assert out[-1]["close"] == 11.5
    assert [b["close"] for b in out[:-1]] == [10.0, 11.0]
    assert len(out) == 3
    # original list/dicts must not be mutated
    assert bars[-1]["close"] == 12.0


def test_substitute_last_close_keeps_ohlc_consistent():
    bars = [_bar(50.0, high=51.0, low=49.0, open_=50.0)]
    above = vp.substitute_last_close(bars, 55.0)
    assert above[-1]["high"] == 55.0  # widened up
    assert above[-1]["low"] == 49.0
    assert above[-1]["open"] == 50.0

    below = vp.substitute_last_close(bars, 45.0)
    assert below[-1]["low"] == 45.0   # widened down
    assert below[-1]["high"] == 51.0


def test_substitute_last_close_rejects_empty():
    import pytest
    with pytest.raises(ValueError, match="empty"):
        vp.substitute_last_close([], 10.0)


def test_regime_flip_alone_counts_as_divergence(monkeypatch):
    same = [_sig("SPY", "ENTRY", "dual_momentum_taa")]
    _patch_signals(monkeypatch, close_sigs=same, proxy_sigs=list(same),
                   regime_close="bullish_trend", regime_proxy="bearish_trend")
    hc, hp = _histories()

    out = vp.decision_divergence(hc, hp, ["SPY"], strategy_rules={})

    assert out["agree"] is False
    assert out["regime_close"] == "bullish_trend"
    assert out["regime_proxy"] == "bearish_trend"
