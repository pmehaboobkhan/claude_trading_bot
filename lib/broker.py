"""Alpaca broker wrapper.

Selects paper vs live keys based on the operating mode in config/approved_modes.yaml.
Refuses live calls until mode == LIVE_EXECUTION. Redacts keys before any logging.

Phase 4 will plug in alpaca-py for real account/positions/orders calls. v1 keeps the
surface minimal: connection check, account snapshot, current positions, latest quote.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from lib.config import current_mode

PAPER_MODES = {"PAPER_TRADING", "LIVE_PROPOSALS", "LIVE_EXECUTION"}
LIVE_MODES = {"LIVE_EXECUTION"}


class BrokerError(RuntimeError):
    """Raised when broker access is refused or misconfigured."""


@dataclass(frozen=True)
class BrokerCreds:
    key_id: str
    secret: str
    base_url: str
    is_live: bool

    def redacted(self) -> str:
        return f"<creds is_live={self.is_live} key_id={self.key_id[:4]}…>"


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise BrokerError(f"missing required env var {name}")
    return val


def credentials(*, want_live: bool = False) -> BrokerCreds:
    """Return broker credentials matching the current mode and the caller's intent.

    - want_live=False: paper credentials, allowed if mode in PAPER_MODES.
    - want_live=True : live credentials, allowed only if mode in LIVE_MODES.
    """
    mode = current_mode()
    if want_live:
        if mode not in LIVE_MODES:
            raise BrokerError(f"live broker access refused: mode={mode}, require LIVE_EXECUTION")
        return BrokerCreds(
            key_id=_require_env("ALPACA_LIVE_KEY_ID"),
            secret=_require_env("ALPACA_LIVE_SECRET_KEY"),
            base_url=os.environ.get("ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets"),
            is_live=True,
        )
    if mode not in PAPER_MODES and mode != "RESEARCH_ONLY":
        # research-only allows reading paper account context for research; HALTED does not.
        raise BrokerError(f"broker access refused: mode={mode}")
    return BrokerCreds(
        key_id=_require_env("ALPACA_PAPER_KEY_ID"),
        secret=_require_env("ALPACA_PAPER_SECRET_KEY"),
        base_url=os.environ.get("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets"),
        is_live=False,
    )


def health_check() -> dict:
    """Fetch /v2/account as a connectivity test. Returns dict; raises BrokerError on failure.

    Imports alpaca-py lazily so this module can be imported even when the SDK isn't installed
    (e.g., during early scaffold work before `pip install -r requirements.txt`).
    """
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover - alpaca-py optional during scaffold
        raise BrokerError(
            "alpaca-py not installed. Run `pip install -r requirements.txt`."
        ) from exc

    creds = credentials(want_live=False)
    client = TradingClient(creds.key_id, creds.secret, paper=not creds.is_live)
    acct = client.get_account()
    return {
        "account_number": acct.account_number,
        "status": str(acct.status),
        "buying_power": float(acct.buying_power),
        "equity": float(acct.equity),
        "is_paper": not creds.is_live,
    }


def get_positions() -> list[dict]:
    """Return current positions as plain dicts. Read-only."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = TradingClient(creds.key_id, creds.secret, paper=not creds.is_live)
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "avg_entry_price": float(p.avg_entry_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
        }
        for p in positions
    ]


def account_snapshot() -> dict:
    """Fuller account snapshot used by the end_of_day circuit-breaker step.

    Returns the fields needed to compute portfolio equity: `cash`, `equity`,
    `buying_power`, `portfolio_value`, plus `is_paper` so callers can sanity-check
    they're on the paper account.
    """
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = TradingClient(creds.key_id, creds.secret, paper=not creds.is_live)
    acct = client.get_account()
    return {
        "account_number": acct.account_number,
        "status": str(acct.status),
        "cash": float(acct.cash),
        "equity": float(acct.equity),
        "buying_power": float(acct.buying_power),
        "portfolio_value": float(acct.portfolio_value),
        "is_paper": not creds.is_live,
    }


def latest_quotes_for_positions() -> dict[str, float]:
    """Return {symbol: latest_mid_price} for every currently open position.

    Used by the end_of_day circuit-breaker step to mark portfolio equity to
    market. Missing/zero quotes raise BrokerError so stale-data conditions
    surface rather than silently zero out positions.
    """
    from lib import data

    positions = get_positions()
    quotes: dict[str, float] = {}
    for p in positions:
        q = data.get_latest_quote(p["symbol"])
        if q.last_price <= 0:
            raise BrokerError(f"stale/zero quote for open position {p['symbol']}")
        quotes[p["symbol"]] = q.last_price
    return quotes


# ---------------------------------------------------------------------------
# Order placement (paper-mirror mode — see lib.paper_sim BROKER_PAPER=alpaca)
# ---------------------------------------------------------------------------
# Live orders are STILL refused unless mode == LIVE_EXECUTION via credentials().
# Paper orders go to Alpaca's paper sandbox at https://paper-api.alpaca.markets.

def submit_market_order(symbol: str, *, qty: float, side: str,
                        client_order_id: str | None = None,
                        time_in_force: str = "day") -> dict:
    """Submit a market order to the broker (paper sandbox in PAPER_TRADING mode).

    Args:
      symbol: Equity ticker.
      qty: Share quantity (positive). Fractional shares supported.
      side: "BUY" or "SELL".
      client_order_id: Optional client-side ID for idempotency. Caller should pass
        a value derived from `decisions/<date>/<HHMM>_<sym>.json` so the order is
        traceable back to the decision file.
      time_in_force: "day" (default) | "gtc" | "ioc" | "fok".

    Returns the broker's order acknowledgement as a plain dict. Does NOT wait
    for the fill — use the returned `id` to poll if a synchronous result is needed.
    """
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    if side.upper() not in ("BUY", "SELL"):
        raise BrokerError(f"invalid side {side!r}; expected BUY or SELL")
    if qty <= 0:
        raise BrokerError(f"qty must be positive, got {qty}")

    creds = credentials(want_live=False)
    client = TradingClient(creds.key_id, creds.secret, paper=not creds.is_live)
    req = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        time_in_force=getattr(TimeInForce, time_in_force.upper()),
        client_order_id=client_order_id,
    )
    order = client.submit_order(order_data=req)
    return {
        "id": str(order.id),
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "qty": float(order.qty),
        "side": str(order.side),
        "status": str(order.status),
        "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        "is_paper": not creds.is_live,
    }


def submit_moc_order(symbol: str, *, qty: float, side: str,
                     client_order_id: str | None = None) -> dict:
    """Submit a Market-On-Close order.

    Fills in the exchange's official closing auction — the same price the
    backtest assumes (`lib.backtest` fills at `bars[-1]["close"]`), keeping
    live paper-mirror results consistent with the validated strategy.

    The exchange requires MOC orders submitted before its cutoff (~15:59 ET;
    earlier on half-days). Submitting after the cutoff is rejected by the
    broker — callers must schedule submission before the cutoff and treat a
    rejection as NO_TRADE for that symbol, never a synthetic fill.
    """
    return submit_market_order(
        symbol, qty=qty, side=side,
        client_order_id=client_order_id, time_in_force="cls",
    )


def get_order(order_id: str) -> dict:
    """Fetch the latest state of a previously-submitted order.

    Used to poll for fill price after `submit_market_order` (which returns
    immediately on submit, not on fill).
    """
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = TradingClient(creds.key_id, creds.secret, paper=not creds.is_live)
    o = client.get_order_by_id(order_id)
    return {
        "id": str(o.id),
        "client_order_id": o.client_order_id,
        "symbol": o.symbol,
        "qty": float(o.qty),
        "filled_qty": float(o.filled_qty or 0),
        "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
        "side": str(o.side),
        "status": str(o.status),
        "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        "filled_at": o.filled_at.isoformat() if o.filled_at else None,
    }


def cancel_all_open_orders() -> int:
    """Cancel every open (unfilled / partially filled) order. Returns count canceled."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = TradingClient(creds.key_id, creds.secret, paper=not creds.is_live)
    responses = client.cancel_orders()
    return len(responses)


def close_all_positions(*, cancel_orders: bool = True) -> list[dict]:
    """Liquidate every open position via market orders. Returns the close-order
    acknowledgements.

    Used by `scripts/sync_alpaca_state.py --reset-fresh-start`. Pairs with
    cancel_all_open_orders to start from a clean broker-side state.
    """
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = TradingClient(creds.key_id, creds.secret, paper=not creds.is_live)
    responses = client.close_all_positions(cancel_orders=cancel_orders)
    out: list[dict] = []
    for r in responses or []:
        try:
            body = r.body if hasattr(r, "body") else r
            order = body if hasattr(body, "id") else getattr(body, "order", None)
            if order is None:
                continue
            out.append({
                "id": str(order.id),
                "symbol": order.symbol,
                "qty": float(order.qty),
                "side": str(order.side),
                "status": str(order.status),
            })
        except (AttributeError, TypeError):
            # Tolerate variations in alpaca-py response shape across versions.
            continue
    return out
