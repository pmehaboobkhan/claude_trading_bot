"""Pure tests for the operating-mode behavior table."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.operating_mode import (  # noqa: E402
    ALL_MODES, MODE_BEHAVIORS, is_writable, is_learning_action_allowed,
    is_trading_action_allowed, mode_summary,
)


def test_all_modes_present():
    assert set(ALL_MODES) == {
        "RESEARCH_ONLY", "PAPER_TRADING", "SAFE_MODE",
        "LIVE_PROPOSALS", "LIVE_EXECUTION", "HALTED",
    }


def test_safe_mode_permits_paper_trades():
    assert is_trading_action_allowed("SAFE_MODE", "paper_buy") is True
    assert is_trading_action_allowed("SAFE_MODE", "paper_close") is True


def test_safe_mode_forbids_live_actions():
    assert is_trading_action_allowed("SAFE_MODE", "live_buy") is False
    assert is_trading_action_allowed("SAFE_MODE", "propose_live_buy") is False


def test_safe_mode_forbids_learning_writes():
    """memory/ writes are blocked under SAFE_MODE except daily_snapshots."""
    assert is_writable("SAFE_MODE", "memory/symbol_profiles/AAPL.md") is False
    assert is_writable("SAFE_MODE", "memory/prediction_reviews/2026-05-12.md") is False
    assert is_writable("SAFE_MODE", "memory/agent_performance/news_sentiment.md") is False
    # Operational snapshots are NOT learning; still allowed.
    assert is_writable("SAFE_MODE", "memory/daily_snapshots/2026-05-12.md") is True


def test_safe_mode_forbids_proposal_writes():
    assert is_writable("SAFE_MODE", "prompts/proposed_updates/2026-05-12_news.md") is False


def test_safe_mode_permits_operational_writes():
    """Journals, decisions, paper trades, logs, reports all remain writable."""
    for path in [
        "journals/daily/2026-05-12.md",
        "decisions/2026-05-12/0935_SPY.json",
        "decisions/by_symbol/SPY.md",
        "trades/paper/log.csv",
        "trades/paper/positions.json",
        "trades/paper/circuit_breaker.json",
        "logs/routine_runs/2026-05-12_eod.md",
        "logs/risk_events/2026-05-12_drawdown.md",
        "reports/end_of_day/2026-05-12.md",
        "data/market/2026-05-12/spy.json",
    ]:
        assert is_writable("SAFE_MODE", path) is True, f"should be writable: {path}"


def test_safe_mode_forbids_learning_actions():
    assert is_learning_action_allowed("SAFE_MODE", "memory_update") is False
    assert is_learning_action_allowed("SAFE_MODE", "prompt_proposal") is False
    assert is_learning_action_allowed("SAFE_MODE", "agent_performance_update") is False
    assert is_learning_action_allowed("SAFE_MODE", "regime_observation") is False


def test_paper_trading_permits_learning():
    """Default mode permits all learning actions (sanity check)."""
    assert is_learning_action_allowed("PAPER_TRADING", "memory_update") is True
    assert is_learning_action_allowed("PAPER_TRADING", "prompt_proposal") is True


def test_halted_forbids_everything_trading():
    assert is_trading_action_allowed("HALTED", "paper_buy") is False
    assert is_trading_action_allowed("HALTED", "live_buy") is False


def test_research_only_forbids_paper_buy_but_permits_learning():
    assert is_trading_action_allowed("RESEARCH_ONLY", "paper_buy") is False
    assert is_learning_action_allowed("RESEARCH_ONLY", "memory_update") is True


def test_mode_summary_returns_dict_with_required_keys():
    summary = mode_summary("SAFE_MODE")
    assert "trading" in summary
    assert "learning" in summary
    assert "writable_roots" in summary
    assert "blocked_roots" in summary
    assert "memory/" in summary["blocked_roots"]
    assert "memory/daily_snapshots/" in summary["writable_subpaths"]


def test_unknown_mode_raises():
    import pytest
    with pytest.raises(ValueError):
        is_writable("MADE_UP_MODE", "anything")
