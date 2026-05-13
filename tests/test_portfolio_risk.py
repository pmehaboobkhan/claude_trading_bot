"""Unit tests for lib/portfolio_risk.py — Path Z circuit-breaker state machine.

Locks in the behaviour decided 2026-05-11. See plan.md "Drawdown decision —
RESOLVED" and reports/learning/pivot_validation_2026-05-10.md for the evidence
that drove the chosen thresholds.

Run with: pytest tests/test_portfolio_risk.py -v
"""
from __future__ import annotations

import json

import pytest

from lib import portfolio_risk
from lib.portfolio_risk import (
    CircuitBreakerState,
    CircuitBreakerThresholds,
    advance,
    exposure_fraction,
    from_config,
    load_state,
    save_state,
    step,
)


def _replay(
    equities: list[float],
    *,
    thresholds: CircuitBreakerThresholds | None = None,
    initial: CircuitBreakerState | None = None,
) -> list[portfolio_risk.CircuitBreakerStep]:
    """Run a sequence of equity observations through the state machine."""
    th = thresholds or CircuitBreakerThresholds()
    state = initial or CircuitBreakerState()
    results = []
    for eq in equities:
        out = step(state, eq, th)
        results.append(out)
        state = out.new_state
    return results


# ---------------------------------------------------------------------------
# Threshold dataclass invariants
# ---------------------------------------------------------------------------

def test_default_thresholds_match_path_z_decision() -> None:
    th = CircuitBreakerThresholds()
    assert th.half_dd == 0.08
    assert th.out_dd == 0.12
    assert th.half_to_full_recover_dd == 0.05
    assert th.out_to_half_recover_dd == 0.08


def test_invalid_half_above_out_rejected() -> None:
    with pytest.raises(ValueError, match="half_dd"):
        CircuitBreakerThresholds(half_dd=0.15, out_dd=0.10)


def test_recovery_threshold_must_be_below_trigger() -> None:
    with pytest.raises(ValueError, match="half_to_full_recover_dd"):
        CircuitBreakerThresholds(half_dd=0.08, half_to_full_recover_dd=0.10)


def test_out_recovery_must_satisfy_ordering() -> None:
    with pytest.raises(ValueError, match="out_to_half_recover_dd"):
        # If out_to_half_recover < half_to_full, OUT → HALF is stricter than
        # HALF → FULL — inverts the intended "OUT recovers faster" design.
        CircuitBreakerThresholds(
            half_to_full_recover_dd=0.07, out_to_half_recover_dd=0.04
        )


# ---------------------------------------------------------------------------
# exposure_fraction
# ---------------------------------------------------------------------------

def test_exposure_fraction_matches_design() -> None:
    assert exposure_fraction("FULL") == 1.0
    assert exposure_fraction("HALF") == 0.5
    assert exposure_fraction("OUT") == 0.0


# ---------------------------------------------------------------------------
# Step behaviour: peak tracking and drawdown
# ---------------------------------------------------------------------------

def test_first_step_initialises_peak() -> None:
    out = step(CircuitBreakerState(), 100_000, CircuitBreakerThresholds())
    assert out.new_state.peak_equity == 100_000
    assert out.drawdown == 0.0
    assert out.new_state.state == "FULL"
    assert out.transitioned is False


def test_peak_only_increases() -> None:
    results = _replay([100, 110, 105, 120, 115])
    peaks = [r.new_state.peak_equity for r in results]
    assert peaks == [100, 110, 110, 120, 120]


def test_drawdown_floors_at_zero_when_at_peak() -> None:
    results = _replay([100, 110, 120, 130])
    assert all(r.drawdown == 0.0 for r in results)


def test_negative_equity_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        step(CircuitBreakerState(), -1.0, CircuitBreakerThresholds())


# ---------------------------------------------------------------------------
# FULL → HALF trigger
# ---------------------------------------------------------------------------

def test_full_to_half_fires_at_threshold() -> None:
    # Peak at 100; 92 is exactly 8% DD — boundary triggers.
    results = _replay([100, 92])
    assert results[0].new_state.state == "FULL"
    assert results[1].new_state.state == "HALF"
    assert results[1].transitioned is True
    assert results[1].previous_state == "FULL"


def test_full_does_not_step_to_half_at_seven_percent() -> None:
    # 7% DD is below the 8% trigger; remain FULL.
    results = _replay([100, 93])
    assert results[1].new_state.state == "FULL"
    assert results[1].transitioned is False


# ---------------------------------------------------------------------------
# HALF → OUT trigger (no skipping FULL → OUT in one observation)
# ---------------------------------------------------------------------------

def test_half_to_out_fires_at_threshold() -> None:
    # 100 → 91 enters HALF; 88 (12% DD) flips to OUT.
    results = _replay([100, 91, 88])
    assert [r.new_state.state for r in results] == ["FULL", "HALF", "OUT"]


def test_one_transition_per_step_no_full_to_out_jump() -> None:
    # A single 20% crash in one observation only steps FULL → HALF this step.
    # OUT requires a subsequent step.
    results = _replay([100, 80])
    assert results[1].new_state.state == "HALF"  # not OUT
    assert results[1].drawdown == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# HALF → FULL recovery (5% threshold, hysteresis below 8% trigger)
# ---------------------------------------------------------------------------

def test_half_recovers_to_full_at_five_percent_dd() -> None:
    # Drop to HALF (10% DD), then recover to 4% DD — should flip back to FULL.
    results = _replay([100, 90, 96])
    assert [r.new_state.state for r in results] == ["FULL", "HALF", "FULL"]


def test_half_does_not_recover_at_six_percent_dd() -> None:
    # 6% DD is above the 5% recovery threshold; stays HALF.
    results = _replay([100, 90, 94])
    assert [r.new_state.state for r in results] == ["FULL", "HALF", "HALF"]


def test_no_full_half_whipsaw_inside_hysteresis_band() -> None:
    # Drop into HALF, then bob around 6-7% DD: stays in HALF the whole time.
    # This is the test that catches the 8/8 symmetric variant's whipsaw bug.
    results = _replay([100, 91, 93, 91, 93, 92, 94, 91])
    states = [r.new_state.state for r in results]
    # After the initial drop to HALF, we never re-enter FULL because DD stays
    # in (0.05, 0.09) — neither recovery nor OUT trigger.
    assert states == ["FULL", "HALF", "HALF", "HALF", "HALF", "HALF", "HALF", "HALF"]


# ---------------------------------------------------------------------------
# OUT → HALF recovery (8% threshold — fast recovery from cash)
# ---------------------------------------------------------------------------

def test_out_recovers_to_half_at_eight_percent_dd() -> None:
    # 100 → 91 → 87 puts us in OUT (13% DD).
    # Recovery to 92 (8% DD) steps up to HALF.
    results = _replay([100, 91, 87, 92])
    assert [r.new_state.state for r in results] == ["FULL", "HALF", "OUT", "HALF"]


def test_out_does_not_recover_above_eight_percent_dd() -> None:
    # Recovery to 91 (9% DD) still above OUT → HALF threshold; stays OUT.
    results = _replay([100, 91, 87, 91])
    assert [r.new_state.state for r in results] == ["FULL", "HALF", "OUT", "OUT"]


def test_out_to_half_to_full_takes_two_steps() -> None:
    # OUT, then full recovery to peak. State must walk OUT → HALF → FULL,
    # one transition per observation.
    results = _replay([100, 91, 87, 95, 100])
    assert [r.new_state.state for r in results] == [
        "FULL", "HALF", "OUT", "HALF", "FULL",
    ]


# ---------------------------------------------------------------------------
# Custom-config behaviour: looser thresholds should NOT trigger at defaults
# ---------------------------------------------------------------------------

def test_thresholds_are_honoured() -> None:
    # Looser thresholds: half at 15%, out at 25%. A 10% DD shouldn't trigger.
    th = CircuitBreakerThresholds(
        half_dd=0.15, out_dd=0.25,
        half_to_full_recover_dd=0.05, out_to_half_recover_dd=0.10,
    )
    results = _replay([100, 90], thresholds=th)
    assert results[1].new_state.state == "FULL"


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------

def test_from_config_returns_defaults_on_missing_block() -> None:
    th = from_config(None)
    assert th == CircuitBreakerThresholds()


def test_from_config_reads_partial_overrides() -> None:
    th = from_config({"half_dd": 0.10, "out_dd": 0.20})
    assert th.half_dd == 0.10
    assert th.out_dd == 0.20
    # Other fields fall through to defaults.
    assert th.half_to_full_recover_dd == 0.05
    assert th.out_to_half_recover_dd == 0.08


def test_from_config_validates_invariants() -> None:
    # Same invariant checks fire when loaded from a config dict.
    with pytest.raises(ValueError):
        from_config({"half_dd": 0.20, "out_dd": 0.10})


# ---------------------------------------------------------------------------
# Reproducibility: same equity sequence → same transitions
# ---------------------------------------------------------------------------

def test_step_is_deterministic() -> None:
    equities = [100, 110, 105, 95, 90, 88, 92, 95, 100, 95, 88]
    a = _replay(equities)
    b = _replay(equities)
    a_facts = [(r.new_state.state, r.new_state.peak_equity,
                round(r.drawdown, 6), r.transitioned) for r in a]
    b_facts = [(r.new_state.state, r.new_state.peak_equity,
                round(r.drawdown, 6), r.transitioned) for r in b]
    assert a_facts == b_facts


# ---------------------------------------------------------------------------
# Persistence: load_state / save_state / advance
# ---------------------------------------------------------------------------

def test_load_state_returns_default_when_file_missing(tmp_path) -> None:
    state = load_state(tmp_path / "missing.json")
    assert state == CircuitBreakerState()


def test_save_then_load_roundtrip(tmp_path) -> None:
    p = tmp_path / "cb.json"
    save_state(CircuitBreakerState(state="HALF", peak_equity=123_456.78), path=p)
    loaded = load_state(p)
    assert loaded.state == "HALF"
    assert loaded.peak_equity == 123_456.78


def test_save_state_records_diagnostic_equity(tmp_path) -> None:
    p = tmp_path / "cb.json"
    save_state(CircuitBreakerState(state="FULL", peak_equity=100_000.0),
               path=p, last_observed_equity=98_500.0)
    payload = json.loads(p.read_text())
    assert payload["last_observed_equity"] == 98_500.0
    assert "updated_at" in payload


def test_advance_loads_steps_and_saves(tmp_path) -> None:
    p = tmp_path / "cb.json"
    h = tmp_path / "h.jsonl"
    # First call: no state file yet → fresh state, equity becomes peak.
    r1 = advance(100_000.0, CircuitBreakerThresholds(), path=p, history_path=h)
    assert r1.new_state.state == "FULL"
    assert r1.new_state.peak_equity == 100_000.0
    # Second call with a 9% drop → should trigger HALF and persist.
    r2 = advance(91_000.0, CircuitBreakerThresholds(), path=p, history_path=h)
    assert r2.transitioned is True
    assert r2.new_state.state == "HALF"
    # Third call: state must be reloaded from disk, not re-initialised.
    r3 = advance(91_500.0, CircuitBreakerThresholds(), path=p, history_path=h)
    assert r3.new_state.state == "HALF"  # still HALF, no whipsaw
    assert r3.new_state.peak_equity == 100_000.0  # peak preserved


def test_advance_persists_state_across_calls(tmp_path) -> None:
    p = tmp_path / "cb.json"
    h = tmp_path / "h.jsonl"
    advance(100_000.0, CircuitBreakerThresholds(), path=p, history_path=h)
    advance(85_000.0, CircuitBreakerThresholds(), path=p, history_path=h)  # 15% DD → HALF
    advance(83_000.0, CircuitBreakerThresholds(), path=p, history_path=h)  # 17% DD → OUT
    # File should now reflect OUT state.
    loaded = load_state(p)
    assert loaded.state == "OUT"
    assert loaded.peak_equity == 100_000.0


# ---------------------------------------------------------------------------
# lib/paper_sim.portfolio_equity — used by routine code feeding advance()
# ---------------------------------------------------------------------------

def test_portfolio_equity_long_position(tmp_path, monkeypatch) -> None:
    from lib import paper_sim
    monkeypatch.setattr(paper_sim, "POSITIONS_PATH", tmp_path / "positions.json")
    (tmp_path / "positions.json").write_text(json.dumps({
        "AAPL": {"side": "BUY", "quantity": 50, "entry_price": 180.0,
                 "entry_ts": "2026-05-09T13:30:00Z",
                 "stop_loss": 175.0, "take_profit": 195.0,
                 "rationale_link": "decisions/2026-05-09/0930_AAPL.json"},
    }))
    eq = paper_sim.portfolio_equity({"AAPL": 190.0}, cash_balance=10_000.0)
    # 10_000 cash + 50 * 190 = 19_500
    assert eq == 19_500.0


def test_portfolio_equity_short_position_settles_correctly(tmp_path, monkeypatch) -> None:
    from lib import paper_sim
    monkeypatch.setattr(paper_sim, "POSITIONS_PATH", tmp_path / "positions.json")
    (tmp_path / "positions.json").write_text(json.dumps({
        "XYZ": {"side": "SELL", "quantity": 10, "entry_price": 100.0,
                "entry_ts": "2026-05-09T13:30:00Z",
                "stop_loss": 110.0, "take_profit": 90.0,
                "rationale_link": "decisions/2026-05-09/0930_XYZ.json"},
    }))
    # Short: payoff is qty * (2*entry - quote). At entry, that's qty * entry (=$1000).
    # If price drops to 90, payoff is 10*(200-90)=1100 → $100 profit on the short.
    eq = paper_sim.portfolio_equity({"XYZ": 90.0}, cash_balance=0.0)
    assert eq == 1100.0


def test_portfolio_equity_no_positions(tmp_path, monkeypatch) -> None:
    from lib import paper_sim
    monkeypatch.setattr(paper_sim, "POSITIONS_PATH", tmp_path / "positions.json")
    eq = paper_sim.portfolio_equity({}, cash_balance=100_000.0)
    assert eq == 100_000.0


def test_portfolio_equity_missing_quote_raises(tmp_path, monkeypatch) -> None:
    from lib import paper_sim
    monkeypatch.setattr(paper_sim, "POSITIONS_PATH", tmp_path / "positions.json")
    (tmp_path / "positions.json").write_text(json.dumps({
        "AAPL": {"side": "BUY", "quantity": 50, "entry_price": 180.0,
                 "entry_ts": "2026-05-09T13:30:00Z",
                 "stop_loss": 175.0, "take_profit": 195.0,
                 "rationale_link": "decisions/2026-05-09/0930_AAPL.json"},
    }))
    with pytest.raises(KeyError, match="no quote provided"):
        paper_sim.portfolio_equity({}, cash_balance=10_000.0)


def test_portfolio_equity_negative_cash_rejected(tmp_path, monkeypatch) -> None:
    from lib import paper_sim
    monkeypatch.setattr(paper_sim, "POSITIONS_PATH", tmp_path / "positions.json")
    with pytest.raises(ValueError, match="non-negative"):
        paper_sim.portfolio_equity({}, cash_balance=-1.0)


# ---------------------------------------------------------------------------
# History log: circuit_breaker_history.jsonl
# ---------------------------------------------------------------------------

def test_advance_appends_history_on_state_change(tmp_path) -> None:
    """When advance() flips state, it appends a JSONL row to circuit_breaker_history.jsonl."""
    from lib import portfolio_risk as pr

    state_path = tmp_path / "circuit_breaker.json"
    history_path = tmp_path / "circuit_breaker_history.jsonl"

    # Initialise FULL with peak 100; observe equity 91 → DD = 9% → should flip to HALF
    pr.save_state(pr.CircuitBreakerState(state="FULL", peak_equity=100.0),
                  path=state_path, last_observed_equity=100.0)

    pr.advance(
        current_equity=91.0,
        thresholds=pr.CircuitBreakerThresholds(),
        path=state_path,
        history_path=history_path,
    )

    assert history_path.exists(), "history file should be created on first transition"
    rows = [json.loads(line) for line in history_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["from_state"] == "FULL"
    assert row["to_state"] == "HALF"
    assert "timestamp" in row
    assert abs(row["dd_pct"] - 9.0) < 0.01
    assert abs(row["observed_equity"] - 91.0) < 0.01
    assert abs(row["peak_equity"] - 100.0) < 0.01


def test_advance_does_not_append_history_when_state_unchanged(tmp_path) -> None:
    """Steady FULL → FULL must not write to history."""
    from lib import portfolio_risk as pr

    state_path = tmp_path / "circuit_breaker.json"
    history_path = tmp_path / "circuit_breaker_history.jsonl"

    pr.save_state(pr.CircuitBreakerState(state="FULL", peak_equity=100.0),
                  path=state_path, last_observed_equity=100.0)

    pr.advance(
        current_equity=99.5,  # tiny dip, still FULL (DD=0.5% < 8% half_dd)
        thresholds=pr.CircuitBreakerThresholds(),
        path=state_path,
        history_path=history_path,
    )

    assert not history_path.exists() or history_path.read_text().strip() == ""


def test_advance_appends_multiple_transitions_to_history(tmp_path) -> None:
    """Two transitions → two rows; history is genuinely append-only."""
    from lib import portfolio_risk as pr

    state_path = tmp_path / "circuit_breaker.json"
    history_path = tmp_path / "circuit_breaker_history.jsonl"

    pr.save_state(pr.CircuitBreakerState(state="FULL", peak_equity=100.0),
                  path=state_path, last_observed_equity=100.0)

    # First transition: FULL → HALF
    pr.advance(current_equity=91.0,
               thresholds=pr.CircuitBreakerThresholds(),
               path=state_path, history_path=history_path)
    # Second transition: HALF → OUT
    pr.advance(current_equity=87.0,  # 13% DD from peak 100
               thresholds=pr.CircuitBreakerThresholds(),
               path=state_path, history_path=history_path)

    rows = [json.loads(line) for line in history_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    assert (rows[0]["from_state"], rows[0]["to_state"]) == ("FULL", "HALF")
    assert (rows[1]["from_state"], rows[1]["to_state"]) == ("HALF", "OUT")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
