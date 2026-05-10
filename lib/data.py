"""Alpaca market-data wrapper. IEX-only feed (free tier).

Returns plain dicts so it composes easily with JSON-friendly outputs.
Stamps every payload with a freshness timestamp. Caller compares against
risk_limits.yaml > data > max_data_staleness_seconds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from lib.broker import BrokerError, credentials


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    last_price: float
    volume: int
    quote_ts: str  # ISO8601 with timezone
    fetched_ts: str  # when we asked the API
    feed: str = "iex"

    def staleness_seconds(self) -> float:
        return (
            datetime.now(UTC) - datetime.fromisoformat(self.quote_ts.replace("Z", "+00:00"))
        ).total_seconds()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def get_latest_quote(symbol: str) -> Quote:
    """Fetch the latest IEX quote for symbol. Raises BrokerError on failure or stale data."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestQuoteRequest
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = StockHistoricalDataClient(creds.key_id, creds.secret)
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    resp = client.get_stock_latest_quote(req)
    q = resp[symbol]
    return Quote(
        symbol=symbol,
        bid=float(q.bid_price or 0.0),
        ask=float(q.ask_price or 0.0),
        last_price=float(q.ask_price or q.bid_price or 0.0),
        volume=int((q.bid_size or 0) + (q.ask_size or 0)),
        quote_ts=q.timestamp.isoformat() if q.timestamp else _now_iso(),
        fetched_ts=_now_iso(),
    )


def get_bars(symbol: str, *, timeframe: str = "1Day", limit: int = 100) -> list[dict]:
    """Fetch recent OHLCV bars. Used by Technical Analysis Agent for indicators."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = StockHistoricalDataClient(creds.key_id, creds.secret)
    tf_map = {"1Day": TimeFrame.Day, "1Hour": TimeFrame.Hour, "5Min": TimeFrame.Minute}
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf_map[timeframe], limit=limit)
    resp = client.get_stock_bars(req)
    bars = resp.data.get(symbol, [])
    return [
        {
            "ts": b.timestamp.isoformat(),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": int(b.volume),
        }
        for b in bars
    ]
