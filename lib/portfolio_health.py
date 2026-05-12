"""Per-position health assessment for the intraday monitoring routines.

Used by `market_open`, `midday`, and `pre_close` to decide whether any open
paper position should be closed before its strategy's natural exit signal.

Pure: no I/O against the broker, no decisions, no fills. Consumers route
proposed closes through `risk_manager` + `compliance_safety` before calling
`lib.paper_sim.close_position`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POSITIONS_PATH = REPO_ROOT / "trades" / "paper" / "positions.json"


@dataclass(frozen=True)
class PositionHealth:
    """Snapshot of one open position evaluated against its stop/target/age."""
    symbol: str
    side: str                    # "BUY" (long) or "SELL" (short)
    quantity: float
    entry_price: float
    current_price: float
    entry_ts: str                # ISO timestamp
    stop_loss: float | None
    take_profit: float | None
    pnl_pct: float               # signed, e.g. +0.0412 for +4.12%
    pnl_usd: float               # signed dollar pnl on this position
    stop_breached: bool          # True if a stop is set AND current breached it
    target_hit: bool             # True if a target is set AND current reached it
    invalidation_triggers: list[str]   # human-readable reasons to close

    def should_close(self) -> bool:
        return bool(self.invalidation_triggers)


def _read_positions(path: Path | None = None) -> dict[str, dict]:
    p = path or POSITIONS_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _assess_one(symbol: str, pos: dict, quote: float) -> PositionHealth:
    side = pos["side"]
    qty = float(pos["quantity"])
    entry = float(pos["entry_price"])
    stop = float(pos["stop_loss"]) if pos.get("stop_loss") not in (None, "", 0) else None
    target = float(pos["take_profit"]) if pos.get("take_profit") not in (None, "", 0) else None
    entry_ts = str(pos.get("entry_ts", ""))

    if side == "BUY":
        pnl_per_share = quote - entry
        stop_breached = stop is not None and quote <= stop
        target_hit = target is not None and quote >= target
    elif side == "SELL":
        pnl_per_share = entry - quote
        stop_breached = stop is not None and quote >= stop
        target_hit = target is not None and quote <= target
    else:
        raise ValueError(f"unknown side on {symbol}: {side}")

    pnl_usd = pnl_per_share * qty
    pnl_pct = pnl_per_share / entry if entry > 0 else 0.0

    triggers: list[str] = []
    if stop_breached:
        triggers.append(
            f"stop_loss breached: {side} entered at {entry:.4f}, "
            f"stop={stop:.4f}, current={quote:.4f}"
        )
    if target_hit:
        triggers.append(
            f"take_profit hit: {side} entered at {entry:.4f}, "
            f"target={target:.4f}, current={quote:.4f}"
        )

    return PositionHealth(
        symbol=symbol,
        side=side,
        quantity=qty,
        entry_price=entry,
        current_price=quote,
        entry_ts=entry_ts,
        stop_loss=stop,
        take_profit=target,
        pnl_pct=pnl_pct,
        pnl_usd=pnl_usd,
        stop_breached=stop_breached,
        target_hit=target_hit,
        invalidation_triggers=triggers,
    )


def assess_positions(
    quotes: dict[str, float], *, positions_path: Path | None = None
) -> list[PositionHealth]:
    """Assess every open paper position against current quotes.

    Raises KeyError if any open position has no quote — callers must surface
    a stale-data alert rather than silently ignoring positions.
    """
    pos = _read_positions(positions_path)
    out: list[PositionHealth] = []
    for symbol, p in pos.items():
        if symbol not in quotes:
            raise KeyError(
                f"no quote provided for open position {symbol}; cannot assess health"
            )
        out.append(_assess_one(symbol, p, float(quotes[symbol])))
    return out


def positions_to_close(
    quotes: dict[str, float], *, positions_path: Path | None = None
) -> list[PositionHealth]:
    """Filter helper: positions with one or more invalidation triggers."""
    return [h for h in assess_positions(quotes, positions_path=positions_path)
            if h.should_close()]


def health_as_dict(h: PositionHealth) -> dict:
    """JSON-friendly view of a PositionHealth — used by routine prompts when
    serializing to a journal or decision file.
    """
    return asdict(h)
