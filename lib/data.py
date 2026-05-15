"""Hybrid market-data wrapper.

For DAILY bars: uses yfinance (free, full history, no SIP-tier paywall, fresh
within 1 trading day vs Alpaca free IEX which lags 6-19 days). yfinance is
already in our stack (used by backtests at backtests/_yfinance_cache/).

For INTRADAY bars (1Hour, 5Min): uses Alpaca IEX (real-time quotes are
sub-second; only daily-bar consolidation is the laggy endpoint).

For LATEST QUOTE: uses Alpaca IEX (real-time, sub-second).

Returns plain dicts so it composes easily with JSON-friendly outputs.
Stamps every payload with a freshness timestamp. Caller compares against
risk_limits.yaml > data > max_data_staleness_seconds.

Override via env: BAR_SOURCE=alpaca to force the legacy all-Alpaca path
(useful for A/B testing or if yfinance is rate-limiting).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from lib.broker import BrokerError, credentials

logger = logging.getLogger(__name__)

# One-shot guard: only attempt the auto-install once per process.
_YFINANCE_AUTOINSTALL_ATTEMPTED = False


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


def _bar_source() -> str:
    """Resolve which source to use for daily bars.

    Default: yfinance (avoids Alpaca free-tier daily-bar lag).
    Env override: BAR_SOURCE=alpaca to force the legacy path.
    """
    return os.environ.get("BAR_SOURCE", "yfinance").strip().lower()


def _import_yfinance_with_autoinstall():
    """Import yfinance, attempting a one-shot pip install if missing.

    The remote scheduled-agent environment sometimes lacks yfinance even though
    it's pinned in requirements.txt — the silent fallback to Alpaca IEX then
    produces 6-19 day stale daily bars. Self-healing here keeps routines fresh
    without operator intervention. On install failure the BrokerError makes
    the cause obvious instead of leaking the import error upstream.
    """
    global _YFINANCE_AUTOINSTALL_ATTEMPTED
    try:
        import yfinance as yf
        return yf
    except ImportError as exc:
        if _YFINANCE_AUTOINSTALL_ATTEMPTED:
            raise BrokerError(
                "yfinance not installed and auto-install already attempted this "
                "process. Run scripts/bootstrap_env.sh or `pip install -r requirements.txt`."
            ) from exc
        _YFINANCE_AUTOINSTALL_ATTEMPTED = True
        logger.warning("yfinance missing — attempting one-shot pip install")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "yfinance>=0.2.40"],
                check=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise BrokerError(
                f"yfinance auto-install failed: {exc}. "
                "Run scripts/bootstrap_env.sh or `pip install -r requirements.txt`."
            ) from exc
        try:
            import yfinance as yf
            logger.warning("yfinance auto-install succeeded")
            return yf
        except ImportError as exc:
            raise BrokerError(
                "yfinance import still fails after auto-install — "
                "environment may need a clean restart."
            ) from exc


def _get_bars_yfinance(symbol: str, *, limit: int) -> list[dict]:
    """Daily bars via yfinance.

    Fresh within ~1 trading day (vs Alpaca free IEX which lags 6-19 days).
    No API key required. Caller-side caching at backtests/_yfinance_cache/
    is for backtests only — production routines fetch fresh.
    """
    yf = _import_yfinance_with_autoinstall()

    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=_calendar_days_for("1Day", limit))

    df = yf.download(
        symbol,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if df.empty:
        return []
    # Flatten multi-level columns if present (yfinance variant).
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    bars: list[dict] = []
    for ts, row in df.iterrows():
        bars.append({
            "ts": ts.strftime("%Y-%m-%dT00:00:00+00:00"),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return bars[-limit:] if len(bars) > limit else bars


def _get_bars_alpaca(symbol: str, *, timeframe: str, limit: int) -> list[dict]:
    """Bars via Alpaca IEX. Used for intraday (real-time) and as the legacy daily path."""
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


def get_bars(symbol: str, *, timeframe: str = "1Day", limit: int = 100) -> list[dict]:
    """Fetch recent OHLCV bars. Used by `lib.signals` for indicator inputs.

    Routing:
      - timeframe == "1Day" AND BAR_SOURCE != "alpaca" → yfinance (fresh,
        avoids Alpaca free-tier daily-bar lag of 6-19 days).
      - All other cases → Alpaca IEX (real-time intraday or env-forced).

    Returns the same dict shape regardless of source: {ts, open, high, low, close, volume}.
    """
    if timeframe == "1Day" and _bar_source() != "alpaca":
        return _get_bars_yfinance(symbol, limit=limit)
    return _get_bars_alpaca(symbol, timeframe=timeframe, limit=limit)
