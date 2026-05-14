# tests/test_historical_membership.py
"""Pure tests for lib.historical_membership."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import historical_membership as hm  # noqa: E402


def test_members_as_of_uses_year_of_date(tmp_path):
    path = tmp_path / "sp100.json"
    path.write_text(json.dumps({
        "2008": ["LEH", "AIG", "AAPL"],
        "2009": ["AIG", "AAPL"],  # LEH removed
        "2010": ["AAPL", "TSLA"],
    }))
    assert sorted(hm.members_as_of("2008-09-15", path=path)) == ["AAPL", "AIG", "LEH"]
    assert sorted(hm.members_as_of("2009-03-01", path=path)) == ["AAPL", "AIG"]
    assert sorted(hm.members_as_of("2010-12-31", path=path)) == ["AAPL", "TSLA"]


def test_members_as_of_unknown_year_returns_nearest_prior(tmp_path):
    path = tmp_path / "sp100.json"
    path.write_text(json.dumps({
        "2010": ["AAPL", "TSLA"],
        "2015": ["AAPL", "TSLA", "META"],
    }))
    # Years between known anchors fall back to the most recent prior anchor.
    assert sorted(hm.members_as_of("2012-06-01", path=path)) == ["AAPL", "TSLA"]
    # Years before the earliest anchor raise.
    import pytest
    with pytest.raises(ValueError, match="before earliest"):
        hm.members_as_of("2005-01-01", path=path)


def test_validate_universe_passes_when_all_symbols_have_yfinance_data(tmp_path):
    """validate_universe is a stub here — full check requires yfinance.

    The pure-helper version just checks file structure (every key is a
    YYYY string; every value is a non-empty list of uppercase strings).
    Full data-availability check is in scripts/run_survivor_bias_stress.py.
    """
    path = tmp_path / "sp100.json"
    path.write_text(json.dumps({"2010": ["AAPL", "MSFT"]}))
    issues = hm.validate_universe(path=path)
    assert issues == []


def test_validate_universe_flags_lowercase_and_empty():
    """Detects malformed entries."""
    import json
    p = Path("/tmp") / "_bad_sp100.json"
    p.write_text(json.dumps({
        "2010": ["aapl", "MSFT"],   # lowercase
        "20xx": ["AAPL"],            # bad year key
        "2011": [],                  # empty
    }))
    issues = hm.validate_universe(path=p)
    p.unlink()
    assert len(issues) == 3
    issue_text = " ".join(issues)
    assert "lowercase" in issue_text or "uppercase" in issue_text
    assert "year" in issue_text
    assert "empty" in issue_text
