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
