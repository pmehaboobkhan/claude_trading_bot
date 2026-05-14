"""Operating-mode behavior table.

Single source of truth for what each mode permits. Used by:
- Routine prompts (call `is_learning_action_allowed(mode, action)` before
  any learning-write step).
- The `.claude/hooks/safe_mode_writes.sh` hook (parses MODE_BEHAVIORS at
  hook time to decide whether a memory/ write is allowed).
- Subagents (the self_learning agent must check mode at top-of-task).

Adding a new mode: add it to ALL_MODES + MODE_BEHAVIORS + the
`approved_modes.schema.json` enum. Tests in `tests/test_operating_mode.py`
will surface missing entries.
"""
from __future__ import annotations

from typing import Literal

Mode = Literal[
    "RESEARCH_ONLY", "PAPER_TRADING", "SAFE_MODE",
    "LIVE_PROPOSALS", "LIVE_EXECUTION", "HALTED",
]

ALL_MODES: tuple[Mode, ...] = (
    "RESEARCH_ONLY", "PAPER_TRADING", "SAFE_MODE",
    "LIVE_PROPOSALS", "LIVE_EXECUTION", "HALTED",
)


# Path roots that are *always* writable (operational data, audit trail, etc).
_OPERATIONAL_ROOTS = (
    "journals/", "decisions/", "trades/paper/", "logs/",
    "reports/", "data/", "backtests/",
)

# Path roots/subpaths that count as "learning writes".
_LEARNING_ROOTS = (
    "memory/",
    "prompts/proposed_updates/",
)

# Carve-out: even in SAFE_MODE, daily operational snapshots are required
# for circuit-breaker continuity. They live under memory/ for historical
# reasons but are not "learning" output.
_SAFE_MODE_MEMORY_CARVEOUTS = (
    "memory/daily_snapshots/",
)


# Per-mode behavior. Each value:
#   - trading_actions: set of allowed action keys
#   - learning_allowed: whether learning_actions are honored at all
#   - learning_actions: set of action keys (only consulted if learning_allowed)
#   - extra_blocked_paths: tuple of path-prefix strings to deny on top of
#     the implicit deny-list (used by SAFE_MODE to deny memory/ except carveouts).
MODE_BEHAVIORS: dict[Mode, dict] = {
    "RESEARCH_ONLY": {
        "trading_actions": {"no_trade", "watch"},
        "learning_allowed": True,
        "learning_actions": {"memory_update", "prompt_proposal",
                             "agent_performance_update", "regime_observation"},
        "extra_blocked_paths": (),
    },
    "PAPER_TRADING": {
        "trading_actions": {"no_trade", "watch", "paper_buy",
                            "paper_sell", "paper_close"},
        "learning_allowed": True,
        "learning_actions": {"memory_update", "prompt_proposal",
                             "agent_performance_update", "regime_observation"},
        "extra_blocked_paths": (),
    },
    "SAFE_MODE": {
        # Trading: same as PAPER_TRADING — deterministic engine runs.
        "trading_actions": {"no_trade", "watch", "paper_buy",
                            "paper_sell", "paper_close"},
        # Learning: SUPPRESSED. The whole point of the mode.
        "learning_allowed": False,
        "learning_actions": set(),
        # File-level enforcement: deny anything under memory/ or
        # prompts/proposed_updates/ except the daily-snapshot carveout.
        "extra_blocked_paths": ("memory/", "prompts/proposed_updates/"),
    },
    "LIVE_PROPOSALS": {
        "trading_actions": {"no_trade", "watch", "paper_buy", "paper_sell",
                            "paper_close", "propose_live_buy",
                            "propose_live_sell", "propose_live_close"},
        "learning_allowed": True,
        "learning_actions": {"memory_update", "prompt_proposal",
                             "agent_performance_update", "regime_observation"},
        "extra_blocked_paths": (),
    },
    "LIVE_EXECUTION": {
        "trading_actions": {"no_trade", "watch", "paper_buy", "paper_sell",
                            "paper_close", "propose_live_buy",
                            "propose_live_sell", "propose_live_close",
                            "live_buy", "live_sell", "live_close"},
        "learning_allowed": True,
        "learning_actions": {"memory_update", "prompt_proposal",
                             "agent_performance_update", "regime_observation"},
        "extra_blocked_paths": (),
    },
    "HALTED": {
        "trading_actions": set(),  # Refuses every trading action
        "learning_allowed": False,
        "learning_actions": set(),
        # HALTED doesn't deny memory/ writes — read-only inspection is allowed.
        "extra_blocked_paths": (),
    },
}


def _check_known(mode: str) -> None:
    if mode not in MODE_BEHAVIORS:
        raise ValueError(
            f"unknown operating mode '{mode}'. "
            f"Known: {', '.join(sorted(MODE_BEHAVIORS.keys()))}"
        )


def is_trading_action_allowed(mode: str, action: str) -> bool:
    _check_known(mode)
    return action in MODE_BEHAVIORS[mode]["trading_actions"]


def is_learning_action_allowed(mode: str, action: str) -> bool:
    _check_known(mode)
    behavior = MODE_BEHAVIORS[mode]
    if not behavior["learning_allowed"]:
        return False
    return action in behavior["learning_actions"]


def is_writable(mode: str, repo_relative_path: str) -> bool:
    """Whether the mode permits a write to the given path (relative to repo root).

    Logic:
      - Always-blocked roots (config/, .claude/agents/, prompts/agents/,
        prompts/routines/, trades/live/) are handled by other hooks
        (block_prompt_overwrites.sh, block_live.sh) — not here.
      - extra_blocked_paths from MODE_BEHAVIORS apply.
      - Carveouts: memory/daily_snapshots/ is always writable (operational).
    """
    _check_known(mode)
    p = repo_relative_path.lstrip("/")

    for carveout in _SAFE_MODE_MEMORY_CARVEOUTS:
        if p.startswith(carveout):
            return True

    for blocked_prefix in MODE_BEHAVIORS[mode]["extra_blocked_paths"]:
        if p.startswith(blocked_prefix):
            return False

    return True


def mode_summary(mode: str) -> dict:
    """Human-friendly summary of a mode's behavior. Used by routine prompts to
    log what mode they ran under and what was/wasn't permitted."""
    _check_known(mode)
    b = MODE_BEHAVIORS[mode]
    return {
        "mode": mode,
        "trading": sorted(b["trading_actions"]),
        "learning": sorted(b["learning_actions"]) if b["learning_allowed"] else "SUPPRESSED",
        "writable_roots": list(_OPERATIONAL_ROOTS),
        "writable_subpaths": list(_SAFE_MODE_MEMORY_CARVEOUTS),
        "blocked_roots": list(b["extra_blocked_paths"]),
    }
