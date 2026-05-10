"""Read repo configs. Single source of truth for which file maps to which dict."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing config: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def watchlist() -> dict[str, Any]:
    return _load_yaml("watchlist.yaml")


def risk_limits() -> dict[str, Any]:
    return _load_yaml("risk_limits.yaml")


def strategy_rules() -> dict[str, Any]:
    return _load_yaml("strategy_rules.yaml")


def routine_schedule() -> dict[str, Any]:
    return _load_yaml("routine_schedule.yaml")


def approved_modes() -> dict[str, Any]:
    return _load_yaml("approved_modes.yaml")


def current_mode() -> str:
    return approved_modes()["mode"]


def is_symbol_approved(symbol: str, action: str = "paper_trading") -> bool:
    """Return True if symbol is in watchlist with the requested approved_for_<action> flag."""
    flag = f"approved_for_{action}"
    for s in watchlist().get("symbols", []):
        if s["symbol"].upper() == symbol.upper():
            return bool(s.get(flag, False))
    return False
