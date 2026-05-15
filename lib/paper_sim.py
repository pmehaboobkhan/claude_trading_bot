"""Paper-trade simulator with optional Alpaca-mirror mode.

Maintains:
  - trades/paper/log.csv         (append-only)
  - trades/paper/positions.json  (current open positions)

Two modes, controlled by env BROKER_PAPER:
  - "sim" (default): pure CSV simulator with synthetic fills via lib.fills.
  - "alpaca": every open/close ALSO submits a market order to the Alpaca
    paper sandbox via lib.broker. The log records the REAL fill price (when
    available within the wait window) and computes the slippage vs the sim
    fill. positions.json reflects the real fill price.

Both are reconciled at end-of-day. Hook #12 enforces append-only on log.csv.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from lib.fills import FillModel, commission, simulated_fill_price

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
PAPER_DIR = REPO_ROOT / "trades" / "paper"
LOG_PATH = PAPER_DIR / "log.csv"
POSITIONS_PATH = PAPER_DIR / "positions.json"

# How long to wait for a market order to fill before falling back to sim price.
# Alpaca paper market orders typically fill in <1s during regular hours.
ALPACA_FILL_POLL_SECONDS = 5.0
ALPACA_FILL_POLL_INTERVAL = 0.5


def broker_mode() -> str:
    """'sim' (default) or 'alpaca'. Controls whether open/close mirrors to broker."""
    return os.environ.get("BROKER_PAPER", "sim").strip().lower()


def _client_order_id(rationale_link: str, side: str) -> str:
    """Stable, traceable client_order_id derived from the decision file path.

    Alpaca caps client_order_id at 128 chars; we comfortably stay under that.
    Including the side disambiguates open vs close on the same decision file.
    """
    base = rationale_link.replace("/", "_").replace(".json", "")
    return f"{base}_{side.lower()}"[:128]


def _alpaca_submit_and_wait(*, symbol: str, qty: float, side: str,
                            client_order_id: str) -> tuple[float | None, dict]:
    """Submit a market order and poll briefly for the fill.

    Returns (filled_avg_price_or_None, last_order_dict). On any error,
    returns (None, {"error": "..."}) so the caller can decide to fall back
    to the sim fill price rather than crashing the routine.
    """
    from lib import broker

    try:
        ack = broker.submit_market_order(
            symbol, qty=qty, side=side.upper(), client_order_id=client_order_id,
        )
    except broker.BrokerError as exc:
        logger.warning("alpaca submit failed for %s %s %s: %s", side, qty, symbol, exc)
        return None, {"error": str(exc)}

    deadline = time.monotonic() + ALPACA_FILL_POLL_SECONDS
    last = ack
    while time.monotonic() < deadline:
        try:
            last = broker.get_order(ack["id"])
        except broker.BrokerError as exc:
            logger.warning("alpaca get_order failed for %s: %s", ack["id"], exc)
            break
        if last.get("filled_avg_price") is not None and last.get("status") == "filled":
            return float(last["filled_avg_price"]), last
        if last.get("status") in ("rejected", "canceled", "expired"):
            return None, last
        time.sleep(ALPACA_FILL_POLL_INTERVAL)
    return None, last

LOG_HEADER = [
    "timestamp",
    "symbol",
    "side",
    "quantity",
    "simulated_price",
    "rationale_link",
    "stop_loss",
    "take_profit",
    "status",
    "realized_pnl",
    "notes",
]


@dataclass
class PaperFill:
    timestamp: str
    symbol: str
    side: str  # BUY | SELL | CLOSE
    quantity: float
    simulated_price: float
    rationale_link: str
    stop_loss: float | None
    take_profit: float | None
    status: str = "OPEN"
    realized_pnl: float = 0.0
    notes: str = ""


def _ensure_log() -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        with LOG_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(LOG_HEADER)


def _read_positions() -> dict[str, dict]:
    if not POSITIONS_PATH.exists():
        return {}
    return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))


def _write_positions(pos: dict[str, dict]) -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    POSITIONS_PATH.write_text(json.dumps(pos, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_fill(fill: PaperFill) -> None:
    """Append a single fill row to log.csv. Append-only by construction."""
    _ensure_log()
    row = [
        fill.timestamp,
        fill.symbol,
        fill.side,
        fill.quantity,
        fill.simulated_price,
        fill.rationale_link,
        fill.stop_loss if fill.stop_loss is not None else "",
        fill.take_profit if fill.take_profit is not None else "",
        fill.status,
        fill.realized_pnl,
        fill.notes,
    ]
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def open_position(*, symbol: str, side: str, quantity: float, quote_price: float,
                  rationale_link: str, stop_loss: float, take_profit: float,
                  notes: str = "", fill_model: FillModel | None = None) -> PaperFill:
    """Open a position with realistic slippage + spread (sim) and optional broker mirror.

    `quote_price` is the latest market quote at decision time. The actual fill price
    applied to the log includes slippage + half-spread per `lib.fills`.

    When env BROKER_PAPER == "alpaca", also submits a market order to the Alpaca
    paper sandbox via lib.broker. The log's simulated_price column reflects the
    broker fill price (when available) so positions.json + log.csv stay aligned
    with the actual broker-side state.
    """
    sim_price = simulated_fill_price(side=side, quote_price=quote_price, model=fill_model)
    fee = commission(model=fill_model)

    # Optional Alpaca-mirror submission. Returns broker fill price or None on failure.
    broker_fill_price: float | None = None
    broker_note = ""
    if broker_mode() == "alpaca":
        coid = _client_order_id(rationale_link, "open")
        broker_fill_price, last_ack = _alpaca_submit_and_wait(
            symbol=symbol, qty=quantity, side=side, client_order_id=coid,
        )
        if broker_fill_price is not None:
            slippage_vs_sim = broker_fill_price - sim_price
            broker_note = (f"; broker_fill={broker_fill_price:.4f}"
                           f" slippage_vs_sim={slippage_vs_sim:+.4f}"
                           f" order_id={last_ack.get('id', '?')}")
        else:
            broker_note = (f"; broker_submit_failed status={last_ack.get('status', 'error')}"
                           f" — fell back to sim price")

    # Use broker fill price if available, else the simulated price.
    fill_price = broker_fill_price if broker_fill_price is not None else sim_price
    fill = PaperFill(
        timestamp=datetime.now(UTC).isoformat(),
        symbol=symbol,
        side=side,
        quantity=quantity,
        simulated_price=round(fill_price, 4),
        rationale_link=rationale_link,
        stop_loss=stop_loss,
        take_profit=take_profit,
        status="OPEN",
        realized_pnl=round(-fee, 2),  # fee booked at entry
        notes=notes + broker_note,
    )
    append_fill(fill)
    pos = _read_positions()
    pos[symbol] = {
        "side": side,
        "quantity": quantity,
        "entry_price": fill.simulated_price,
        "entry_ts": fill.timestamp,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rationale_link": rationale_link,
    }
    _write_positions(pos)
    return fill


def close_position(symbol: str, *, quote_price: float, rationale_link: str,
                   notes: str = "", fill_model: FillModel | None = None) -> PaperFill:
    """Close a position with realistic slippage and optional broker mirror.

    When env BROKER_PAPER == "alpaca", also submits a closing market order
    (opposite side) to Alpaca. Records the broker fill price + slippage in
    notes; computes realized PnL against the original entry price using the
    broker fill price (or sim price on broker failure).
    """
    pos = _read_positions()
    if symbol not in pos:
        raise KeyError(f"no open paper position for {symbol}")
    p = pos.pop(symbol)
    sim_price = simulated_fill_price(side="CLOSE", quote_price=quote_price, model=fill_model)
    fee = commission(model=fill_model)

    # Closing side is the opposite of the original side.
    close_side = "SELL" if p["side"] == "BUY" else "BUY"
    broker_fill_price: float | None = None
    broker_note = ""
    if broker_mode() == "alpaca":
        coid = _client_order_id(rationale_link, "close")
        broker_fill_price, last_ack = _alpaca_submit_and_wait(
            symbol=symbol, qty=p["quantity"], side=close_side, client_order_id=coid,
        )
        if broker_fill_price is not None:
            slippage_vs_sim = broker_fill_price - sim_price
            broker_note = (f"; broker_close={broker_fill_price:.4f}"
                           f" slippage_vs_sim={slippage_vs_sim:+.4f}"
                           f" order_id={last_ack.get('id', '?')}")
        else:
            broker_note = (f"; broker_close_failed status={last_ack.get('status', 'error')}"
                           f" — fell back to sim price")

    fill_price = broker_fill_price if broker_fill_price is not None else sim_price
    pnl = (fill_price - p["entry_price"]) * p["quantity"] * (1 if p["side"] == "BUY" else -1) - fee
    fill = PaperFill(
        timestamp=datetime.now(UTC).isoformat(),
        symbol=symbol,
        side="CLOSE",
        quantity=p["quantity"],
        simulated_price=round(fill_price, 4),
        rationale_link=rationale_link,
        stop_loss=None,
        take_profit=None,
        status="CLOSED",
        realized_pnl=round(pnl, 2),
        notes=notes + broker_note,
    )
    append_fill(fill)
    _write_positions(pos)
    return fill


RESET_TOKENS = ("RESET", "MARKER", "_RESET_", "_MARKER_")


def _is_reset_row(row: dict) -> bool:
    for field in ("symbol", "side", "status"):
        if row.get(field, "").strip().upper() in RESET_TOKENS:
            return True
    return False


def reconcile() -> dict:
    """Recompute open positions from log.csv and verify it matches positions.json.

    Returns a dict with `discrepancies` listing any mismatches. Used by EOD routine.

    log.csv is append-only. When ``sync_alpaca_state.py --reset-fresh-start``
    runs, it appends a watershed row with ``symbol=_RESET_`` / ``status=RESET``;
    everything above that line is closed at the broker side and ``positions.json``
    is overwritten to ``{}``. We only consider rows AFTER the latest reset
    marker — pre-reset OPENs are stale, not divergence.
    """
    _ensure_log()
    open_from_log: dict[str, dict] = {}
    with LOG_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    last_reset_idx = -1
    for i, row in enumerate(rows):
        if _is_reset_row(row):
            last_reset_idx = i
    live_rows = rows[last_reset_idx + 1 :] if last_reset_idx >= 0 else rows
    for row in live_rows:
        if _is_reset_row(row):
            continue
        sym = row["symbol"]
        if row["status"] == "OPEN":
            open_from_log[sym] = {
                "side": row["side"],
                "quantity": float(row["quantity"]),
                "entry_price": float(row["simulated_price"]),
            }
        elif row["status"] == "CLOSED":
            open_from_log.pop(sym, None)

    on_disk = _read_positions()
    discrepancies = []
    for sym, log_pos in open_from_log.items():
        disk_pos = on_disk.get(sym)
        if not disk_pos:
            discrepancies.append({"symbol": sym, "issue": "open in log, missing on disk"})
            continue
        if abs(log_pos["quantity"] - disk_pos["quantity"]) > 1e-6:
            discrepancies.append({"symbol": sym, "issue": "quantity mismatch"})
    for sym in on_disk:
        if sym not in open_from_log:
            discrepancies.append({"symbol": sym, "issue": "on disk, not open in log"})

    return {"open_count": len(open_from_log), "discrepancies": discrepancies}


def fill_dict(fill: PaperFill) -> dict:
    return asdict(fill)


def portfolio_equity(quotes: dict[str, float], cash_balance: float) -> float:
    """Sum of open-position mark-to-market value plus cash.

    `quotes` maps symbol → latest price. Any symbol present in positions.json
    but missing from `quotes` raises KeyError — callers must surface a stale-
    data alert rather than silently ignore positions. Short positions (`side:
    "SELL"`) contribute as: `quantity * (2 * entry_price - quote_price)`, the
    cash-settled short payoff.

    Used by routine code to compute today's portfolio value before consulting
    the circuit-breaker (`lib.portfolio_risk.advance`).
    """
    if cash_balance < 0:
        raise ValueError(f"cash_balance must be non-negative, got {cash_balance}")
    pos = _read_positions()
    equity = float(cash_balance)
    for sym, p in pos.items():
        if sym not in quotes:
            raise KeyError(
                f"no quote provided for open position {sym}; cannot compute equity"
            )
        qty = float(p["quantity"])
        entry = float(p["entry_price"])
        quote = float(quotes[sym])
        if p["side"] == "BUY":
            equity += qty * quote
        elif p["side"] == "SELL":
            equity += qty * (2 * entry - quote)
        else:
            raise ValueError(f"unknown side on {sym}: {p['side']}")
    return equity
