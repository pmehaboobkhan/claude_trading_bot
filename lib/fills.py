"""Realistic paper-fill modeling.

Live trading reality has slippage and spread costs. A naive paper simulator that
fills at the last quote will overstate edge. This module adds modest, deterministic
friction so paper PnL approximates a real Alpaca paper fill more closely.

Defaults are intentionally pessimistic — we'd rather underestimate edge than over.
"""
from __future__ import annotations

from dataclasses import dataclass

# Default friction parameters (tunable from risk_limits.yaml > fills if desired).
DEFAULT_SLIPPAGE_BPS = 1.0          # 1 basis point per side (0.01%)
DEFAULT_HALF_SPREAD_BPS = 1.0       # additional 1 bp to cross half the spread
DEFAULT_COMMISSION_PER_TRADE = 0.0  # Alpaca: $0 commission on US equities/ETFs


@dataclass(frozen=True)
class FillModel:
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS
    half_spread_bps: float = DEFAULT_HALF_SPREAD_BPS
    commission_per_trade: float = DEFAULT_COMMISSION_PER_TRADE


def simulated_fill_price(*, side: str, quote_price: float,
                         model: FillModel | None = None) -> float:
    """Return a simulated fill price for `side` at `quote_price`.

    Buys fill above the quote; sells/closes fill below. Slippage + half-spread together
    is ~2 bps per side by default — a deliberately pessimistic round-trip cost.
    """
    m = model or FillModel()
    bps_total = (m.slippage_bps + m.half_spread_bps) / 10_000
    if side.upper() == "BUY":
        return quote_price * (1 + bps_total)
    if side.upper() in {"SELL", "CLOSE"}:
        return quote_price * (1 - bps_total)
    raise ValueError(f"unknown side: {side}")


def round_trip_friction_pct(model: FillModel | None = None) -> float:
    """Approximate cost of a round-trip in pct (entry + exit slippage + spread)."""
    m = model or FillModel()
    return 2 * (m.slippage_bps + m.half_spread_bps) / 10_000


def commission(*, model: FillModel | None = None) -> float:
    return (model or FillModel()).commission_per_trade
