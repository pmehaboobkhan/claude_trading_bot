"""Time-aware universe for historical backtests.

For symbols that didn't exist before a certain date (META, TSLA, V),
include them in the Strategy B candidate universe only on or after their
actual listing date. Otherwise the backtest implicitly assumes META
existed in 2008 which biases the top-N selection nonsensically.

This is consumed only by the long-window backtest script. Production
trading uses the present-day watchlist directly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable


# Listing dates for the modern mega-cap basket. Symbols not listed here are
# assumed to predate any window we'd realistically backtest.
# Sources: company SEC filings + yfinance first-available-bar dates.
MEGACAP_LISTING_DATES: dict[str, str] = {
    # Stocks that DID NOT exist before some recent date
    "META":  "2012-05-18",   # IPO as FB
    "TSLA":  "2010-06-29",
    "V":     "2008-03-19",
    "GOOGL": "2004-08-19",
    "GOOG":  "2014-04-03",   # share-class split; GOOGL preceded
    "MA":    "2006-05-25",

    # ETFs
    "SHV":   "2007-01-11",
    "BIL":   "2007-05-30",
    "GLD":   "2004-11-18",
    "IEF":   "2002-07-26",
    "SHY":   "2002-07-26",
    # SPY: 1993-01-29 — predates any realistic window, so omitted (treated as always-tradeable)

    # Modern names that DID exist pre-2008
    "AAPL": "1980-12-12",
    "MSFT": "1986-03-13",
    "AMZN": "1997-05-15",
    "NVDA": "1999-01-22",
    "JPM":  "1980-01-01",
    "BAC":  "1986-01-01",
    "JNJ":  "1980-01-01",
    "UNH":  "1984-10-17",
    "PFE":  "1980-01-01",
    "WMT":  "1980-01-01",
    "COST": "1985-12-05",
    "HD":   "1981-09-22",
    "XOM":  "1980-01-01",
    "ORCL": "1986-03-12",
    "CSCO": "1990-02-16",
}


def tradeable_as_of(symbols: Iterable[str], date_iso: str) -> list[str]:
    """Return the subset of `symbols` that were tradeable on or before `date_iso`.

    Symbols not in MEGACAP_LISTING_DATES are assumed always tradeable
    (conservative — they're likely older than any window we'd backtest).
    """
    target = datetime.strptime(date_iso[:10], "%Y-%m-%d").date()
    out = []
    for sym in symbols:
        listed = MEGACAP_LISTING_DATES.get(sym)
        if listed is None:
            out.append(sym)
            continue
        listed_date = datetime.strptime(listed, "%Y-%m-%d").date()
        if target >= listed_date:
            out.append(sym)
    return out


def filter_bars_by_listing(bars_by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Drop any bar dated before the symbol's listing date.

    yfinance sometimes returns synthesized pre-listing bars (zeros, NaN).
    This is a defensive filter to prevent those polluting downstream
    indicators (especially SMA / momentum windows).
    """
    out: dict[str, list[dict]] = {}
    for sym, bars in bars_by_symbol.items():
        listed = MEGACAP_LISTING_DATES.get(sym)
        if listed is None:
            out[sym] = list(bars)
            continue
        out[sym] = [b for b in bars if b.get("ts", "")[:10] >= listed]
    return out
