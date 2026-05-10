"""Internal paper-trade simulator.

Used in Phase 4 before connecting to Alpaca paper API. Maintains:
  - trades/paper/log.csv         (append-only)
  - trades/paper/positions.json  (current open positions)

Both are reconciled at end-of-day. Hook #12 enforces append-only on log.csv.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from lib.fills import FillModel, commission, simulated_fill_price

REPO_ROOT = Path(__file__).resolve().parent.parent
PAPER_DIR = REPO_ROOT / "trades" / "paper"
LOG_PATH = PAPER_DIR / "log.csv"
POSITIONS_PATH = PAPER_DIR / "positions.json"

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
    """Simulate opening a position with realistic slippage + spread.

    `quote_price` is the latest market quote at decision time. The actual fill price
    applied to the log includes slippage + half-spread per `lib.fills`.
    """
    fill_price = simulated_fill_price(side=side, quote_price=quote_price, model=fill_model)
    fee = commission(model=fill_model)
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
        notes=notes,
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
    """Simulate closing a position with realistic slippage. Computes realized PnL."""
    pos = _read_positions()
    if symbol not in pos:
        raise KeyError(f"no open paper position for {symbol}")
    p = pos.pop(symbol)
    fill_price = simulated_fill_price(side="CLOSE", quote_price=quote_price, model=fill_model)
    fee = commission(model=fill_model)
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
        notes=notes,
    )
    append_fill(fill)
    _write_positions(pos)
    return fill


def reconcile() -> dict:
    """Recompute open positions from log.csv and verify it matches positions.json.

    Returns a dict with `discrepancies` listing any mismatches. Used by EOD routine.
    """
    _ensure_log()
    open_from_log: dict[str, dict] = {}
    with LOG_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
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
