# lib/historical_membership.py
"""Point-in-time S&P 100 membership lookup.

Reads data/historical/sp100_as_of.json (year → [symbols]) and
answers `members_as_of(date_iso)`. Used by the survivor-bias stress
test to feed Strategy B a year-appropriate universe instead of the
modern winners basket.

The JSON file is hand-curated; see docs/historical_universe_methodology.md.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "data" / "historical" / "sp100_as_of.json"


def _load(path: Path | None = None) -> dict[str, list[str]]:
    p = path or DEFAULT_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def members_as_of(date_iso: str, *, path: Path | None = None) -> list[str]:
    """Return the universe active on the given date.

    Strategy: take the entry for `year(date_iso)`. If that year is missing,
    fall back to the most recent prior year. Raises ValueError if the
    date is before the earliest year in the table.
    """
    table = _load(path)
    year_str = date_iso[:4]
    if year_str in table:
        return list(table[year_str])
    # Fall back to most recent prior anchor
    available = sorted(int(y) for y in table.keys() if y.isdigit())
    if not available:
        raise ValueError("empty universe table")
    target = int(year_str)
    priors = [y for y in available if y <= target]
    if not priors:
        earliest = min(available)
        raise ValueError(
            f"date {date_iso} is before earliest universe year {earliest}"
        )
    return list(table[str(priors[-1])])


def all_known_symbols(*, path: Path | None = None) -> list[str]:
    """Union of every symbol that appears in any year of the table.

    Used by the script to build the bar-fetch list — fetch once, slice per-year.
    """
    table = _load(path)
    out: set[str] = set()
    for syms in table.values():
        out.update(syms)
    return sorted(out)


def validate_universe(*, path: Path | None = None) -> list[str]:
    """Structural validation. Returns list of issue strings (empty = OK).

    Checks:
    - Every key is a 4-digit year string
    - Every value is a non-empty list
    - Every symbol is uppercase ASCII
    """
    issues: list[str] = []
    table = _load(path)
    for key, syms in table.items():
        if not (key.isdigit() and len(key) == 4):
            issues.append(f"bad year key: '{key}' (must be 4-digit YYYY)")
            continue
        if not syms:
            issues.append(f"empty universe for year {key}")
            continue
        for s in syms:
            if not isinstance(s, str) or not s.isascii() or not s.isupper():
                issues.append(
                    f"symbol '{s}' in year {key} must be uppercase ASCII"
                )
    return issues
