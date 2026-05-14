"""Pure tests for the time-aware historical universe."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.historical_universe import (  # noqa: E402
    MEGACAP_LISTING_DATES, tradeable_as_of, filter_bars_by_listing,
)


def test_tradeable_as_of_2008_excludes_meta_and_tsla():
    universe = ["AAPL", "MSFT", "META", "TSLA", "NVDA", "GOOGL", "V"]
    result = tradeable_as_of(universe, "2008-01-01")
    assert "AAPL" in result and "MSFT" in result and "NVDA" in result
    assert "META" not in result
    assert "TSLA" not in result
    assert "V" not in result  # V IPO'd March 2008
    assert "GOOGL" in result  # IPO 2004


def test_tradeable_as_of_2013_includes_meta_excludes_nothing_else():
    universe = ["AAPL", "MSFT", "META", "TSLA", "V"]
    result = tradeable_as_of(universe, "2013-01-01")
    assert set(result) == {"AAPL", "MSFT", "META", "TSLA", "V"}


def test_tradeable_as_of_meta_boundary_day_after_listing():
    # META listed 2012-05-18
    assert "META" in tradeable_as_of(["META"], "2012-05-18")
    assert "META" not in tradeable_as_of(["META"], "2012-05-17")


def test_tradeable_as_of_unknown_symbol_assumed_always_tradeable():
    """Symbols not in MEGACAP_LISTING_DATES default to 'always tradeable'."""
    assert "UNKNOWN" in tradeable_as_of(["UNKNOWN"], "1995-01-01")


def test_filter_bars_by_listing_drops_pre_listing_bars():
    """Bars dated before listing must be dropped (yfinance sometimes returns junk)."""
    bars = {
        "AAPL": [{"ts": "2000-01-03T00:00:00Z", "close": 1.0},
                 {"ts": "2008-01-03T00:00:00Z", "close": 10.0}],
        "META": [{"ts": "2010-01-03T00:00:00Z", "close": 1.0},  # pre-listing junk
                 {"ts": "2013-01-03T00:00:00Z", "close": 30.0}],
    }
    filtered = filter_bars_by_listing(bars)
    assert len(filtered["AAPL"]) == 2
    assert len(filtered["META"]) == 1
    assert filtered["META"][0]["ts"].startswith("2013")
