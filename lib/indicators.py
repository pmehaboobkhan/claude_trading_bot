"""Pure technical-indicator computations. No decisions, no I/O.

Every function takes a list of bars (oldest first) or a list of closes and returns
either a number or a list aligned to the input. Numpy/pandas dependencies are kept
minimal so this module loads fast and is unit-testable in isolation.
"""
from __future__ import annotations

from collections.abc import Sequence


def _closes(bars: Sequence[dict]) -> list[float]:
    return [float(b["close"]) for b in bars]


def sma(values: Sequence[float], window: int) -> float | None:
    """Simple moving average over the most recent `window` values. None if insufficient data."""
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def sma_series(values: Sequence[float], window: int) -> list[float | None]:
    """SMA computed at every index (None until window is filled)."""
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - window : i + 1]) / window)
    return out


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    """Wilder's RSI on the trailing window. None if insufficient data."""
    if len(values) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def atr(bars: Sequence[dict], period: int = 14) -> float | None:
    """Average True Range over the trailing `period` bars. None if insufficient data."""
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        high = float(bars[i]["high"])
        low = float(bars[i]["low"])
        prev_close = float(bars[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period


def relative_strength(target_closes: Sequence[float], benchmark_closes: Sequence[float],
                      window: int) -> float | None:
    """Return target's % change over `window` minus benchmark's % change over `window`.

    A positive number means the target outperformed the benchmark over the window.
    """
    if len(target_closes) < window + 1 or len(benchmark_closes) < window + 1:
        return None
    t_change = (target_closes[-1] / target_closes[-window - 1]) - 1.0
    b_change = (benchmark_closes[-1] / benchmark_closes[-window - 1]) - 1.0
    return t_change - b_change


def above_sma(values: Sequence[float], window: int) -> bool | None:
    """True iff the last close is above the SMA(window). None if insufficient data."""
    s = sma(values, window)
    if s is None:
        return None
    return values[-1] > s


def pct_from_sma(values: Sequence[float], window: int) -> float | None:
    """Last close as a fraction above/below SMA(window). None if insufficient data."""
    s = sma(values, window)
    if s is None or s == 0:
        return None
    return (values[-1] / s) - 1.0


def closes(bars: Sequence[dict]) -> list[float]:
    """Public re-export of the close-extraction helper."""
    return _closes(bars)
