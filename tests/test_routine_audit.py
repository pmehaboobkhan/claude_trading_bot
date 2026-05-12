"""Unit tests for lib/routine_audit.py — routine-run audit logs.

Run with: pytest tests/test_routine_audit.py -v
"""
from __future__ import annotations

import pytest
import yaml

from lib import routine_audit
from lib.routine_audit import RoutineAudit, file_record, write_audit


def _audit(**overrides) -> RoutineAudit:
    defaults = dict(
        routine="pre_market",
        started_at="2026-05-12T10:30:00+00:00",
        ended_at="2026-05-12T10:31:23+00:00",
        duration_seconds=83.0,
        exit_reason="clean",
    )
    defaults.update(overrides)
    return RoutineAudit(**defaults)


# ---------------------------------------------------------------------------
# Dataclass invariants
# ---------------------------------------------------------------------------

def test_routine_must_be_snake_case() -> None:
    with pytest.raises(ValueError, match="snake_case"):
        _audit(routine="Pre-Market")


def test_routine_cannot_start_with_digit() -> None:
    with pytest.raises(ValueError, match="snake_case"):
        _audit(routine="1_pre_market")


def test_exit_reason_must_be_valid() -> None:
    with pytest.raises(ValueError, match="exit_reason"):
        _audit(exit_reason="success")


def test_duration_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        _audit(duration_seconds=-1.0)


# ---------------------------------------------------------------------------
# Computed properties
# ---------------------------------------------------------------------------

def test_approximate_input_kb_sums_files_read() -> None:
    audit = _audit(
        files_read=[
            {"path": "config/watchlist.yaml", "bytes": 5_120},   # 5 KB
            {"path": "CLAUDE.md", "bytes": 6_144},               # 6 KB
            {"path": "journals/daily/2026-05-11.md", "bytes": 20_480},  # 20 KB
        ]
    )
    assert audit.approximate_input_kb == 31


def test_approximate_input_kb_is_zero_with_no_reads() -> None:
    assert _audit().approximate_input_kb == 0


def test_total_subagent_dispatches_sums_dict() -> None:
    audit = _audit(subagent_dispatches={"market_data": 1, "news_sentiment": 2,
                                        "technical_analysis": 1})
    assert audit.total_subagent_dispatches == 4


# ---------------------------------------------------------------------------
# write_audit
# ---------------------------------------------------------------------------

def test_write_audit_creates_named_file(tmp_path) -> None:
    audit = _audit()
    out = write_audit(audit, dir_path=tmp_path)
    assert out.name == "2026-05-12_103000_pre_market_audit.md"
    assert out.exists()


def test_write_audit_is_valid_yaml(tmp_path) -> None:
    audit = _audit(
        files_read=[{"path": "CLAUDE.md", "bytes": 6_144}],
        subagent_dispatches={"market_data": 1, "technical_analysis": 1},
        artifacts_written=["reports/pre_market/2026-05-12.md",
                          "journals/daily/2026-05-12.md"],
        commits=["abc1234"],
        notes="signal eval completed; no entries",
    )
    out = write_audit(audit, dir_path=tmp_path)
    loaded = yaml.safe_load(out.read_text())
    assert loaded["routine"] == "pre_market"
    assert loaded["exit_reason"] == "clean"
    assert loaded["approximate_input_kb"] == 6
    assert loaded["total_subagent_dispatches"] == 2
    assert loaded["files_read"] == [{"path": "CLAUDE.md", "bytes": 6_144}]
    assert loaded["artifacts_written"] == [
        "reports/pre_market/2026-05-12.md",
        "journals/daily/2026-05-12.md",
    ]
    assert loaded["commits"] == ["abc1234"]
    assert loaded["notes"] == "signal eval completed; no entries"


def test_write_audit_omits_notes_when_empty(tmp_path) -> None:
    out = write_audit(_audit(), dir_path=tmp_path)
    loaded = yaml.safe_load(out.read_text())
    assert "notes" not in loaded


def test_write_audit_handles_z_suffix_iso_timestamps(tmp_path) -> None:
    audit = _audit(started_at="2026-05-12T10:30:00Z")
    out = write_audit(audit, dir_path=tmp_path)
    assert "2026-05-12_103000_pre_market_audit.md" == out.name


def test_write_audit_handles_fractional_seconds(tmp_path) -> None:
    audit = _audit(started_at="2026-05-12T10:30:00.123456+00:00")
    out = write_audit(audit, dir_path=tmp_path)
    assert "2026-05-12_103000_pre_market_audit.md" == out.name


def test_write_audit_falls_back_to_now_on_unparseable_ts(tmp_path) -> None:
    # Should not raise — falls back to current UTC time.
    audit = _audit(started_at="not-a-timestamp")
    out = write_audit(audit, dir_path=tmp_path)
    assert out.name.endswith("_pre_market_audit.md")


# ---------------------------------------------------------------------------
# file_record helper
# ---------------------------------------------------------------------------

def test_file_record_reads_size_on_disk(tmp_path) -> None:
    p = tmp_path / "fake_config.yaml"
    p.write_text("a" * 1234, encoding="utf-8")
    rec = file_record(p)
    assert rec["bytes"] == 1234
    assert rec["path"].endswith("fake_config.yaml")


def test_file_record_zero_bytes_when_missing() -> None:
    rec = file_record("/tmp/this/path/does/not/exist.txt")
    assert rec["bytes"] == 0


# ---------------------------------------------------------------------------
# End-to-end smoke
# ---------------------------------------------------------------------------

def test_realistic_pre_market_audit_round_trip(tmp_path) -> None:
    # Mimic what an end-of-routine audit would look like.
    audit = _audit(
        routine="pre_market",
        files_read=[
            {"path": "CLAUDE.md", "bytes": 6_500},
            {"path": "config/watchlist.yaml", "bytes": 5_000},
            {"path": "config/risk_limits.yaml", "bytes": 3_000},
            {"path": "config/strategy_rules.yaml", "bytes": 3_000},
            {"path": "memory/daily_snapshots/2026-05-11.md", "bytes": 900},
            {"path": "memory/daily_snapshots/2026-05-10.md", "bytes": 850},
        ],
        subagent_dispatches={
            "market_data": 1, "news_sentiment": 1,
            "macro_sector": 1, "technical_analysis": 1,
        },
        artifacts_written=[
            "reports/pre_market/2026-05-12.md",
            "journals/daily/2026-05-12.md",
        ],
        commits=["d10f9b6"],
    )
    out = write_audit(audit, dir_path=tmp_path)
    loaded = yaml.safe_load(out.read_text())
    assert loaded["approximate_input_kb"] == 18  # well under 200 KB cap
    assert loaded["total_subagent_dispatches"] == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
