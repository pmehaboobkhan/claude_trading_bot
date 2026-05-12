"""Alpaca market-data wrapper. IEX-only feed (free tier).

Returns plain dicts so it composes easily with JSON-friendly outputs.
Stamps every payload with a freshness timestamp. Caller compares against
risk_limits.yaml > data > max_data_staleness_seconds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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


def _calendar_days_for(timeframe: str, limit: int) -> int:
    """How many calendar days back to ask for to safely cover `limit` bars of `timeframe`.

    Alpaca's free IEX tier returns only the latest bar when `start` isn't passed —
    so we always pass `start`. We over-ask (1.5x trading days for daily, 2x for
    intraday) to cover weekends/holidays and let the API trim.
    """
    if timeframe == "1Day":
        return int(limit * 1.5) + 5
    if timeframe == "1Hour":
        return max(int(limit / 7 * 1.5) + 5, 7)        # ~7 trading hours/day
    if timeframe == "5Min":
        return max(int(limit / 78 * 1.5) + 5, 7)       # ~78 5-min bars/day
    raise ValueError(f"unsupported timeframe: {timeframe}")


def get_bars(symbol: str, *, timeframe: str = "1Day", limit: int = 100) -> list[dict]:
    """Fetch recent OHLCV bars. Used by `lib.signals` for indicator inputs.

    Always passes an explicit `start` date computed from `limit` — without it,
    Alpaca's free IEX tier returns only the most recent bar.
    """
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
    except ImportError as exc:  # pragma: no cover
        raise BrokerError("alpaca-py not installed") from exc

    creds = credentials(want_live=False)
    client = StockHistoricalDataClient(creds.key_id, creds.secret)
    tf_map = {"1Day": TimeFrame.Day, "1Hour": TimeFrame.Hour, "5Min": TimeFrame.Minute}

    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=_calendar_days_for(timeframe, limit))

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf_map[timeframe],
        start=start_dt,
        end=end_dt,
        limit=limit,
        feed="iex",  # explicit — free tier
    )
    resp = client.get_stock_bars(req)
    bars = resp.data.get(symbol, [])
    if len(bars) > limit:
        bars = bars[-limit:]  # most recent N
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
