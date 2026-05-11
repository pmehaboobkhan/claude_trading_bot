"""Portfolio-level drawdown circuit-breaker.

Path Z (decided 2026-05-11): a state machine that throttles strategy exposure based
on the running portfolio drawdown. Backtest evidence is in
`reports/learning/pivot_validation_2026-05-10.md` and
`backtests/multi_strategy_portfolio/2013-05-24_to_2026-05-08_path_z_asymmetric_5_8.md`.

States and transitions:

- FULL  (100% strategies, 0% cash)
  → HALF when portfolio drawdown ≥ half_dd (default 8%)
- HALF  (50% strategies, 50% cash in SHV)
  → OUT  when portfolio drawdown ≥ out_dd (default 12%)
  → FULL when portfolio drawdown ≤ half_to_full_recover_dd (default 5%, 3pp below trigger)
- OUT   (0% strategies, 100% cash)
  → HALF when portfolio drawdown ≤ out_to_half_recover_dd (default 8%, 4pp below trigger)

The recovery thresholds are deliberately asymmetric: a tight 3pp band around the
HALF trigger prevents FULL↔HALF whipsaw; a wider 4pp band below the OUT trigger
recovers exposure fast enough to catch post-crash rallies (the symmetric 5%/5%
version sat in cash for 4 years after the 2020 COVID drop).

The pure core (`step`) has no I/O. The persistence helpers (`load_state`,
`save_state`, `advance`) read/write `trades/paper/circuit_breaker.json` for
multi-routine continuity.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "trades" / "paper" / "circuit_breaker.json"

State = Literal["FULL", "HALF", "OUT"]

VALID_STATES: tuple[State, ...] = ("FULL", "HALF", "OUT")

EXPOSURE_FRACTION_BY_STATE: dict[State, float] = {
    "FULL": 1.0,
    "HALF": 0.5,
    "OUT": 0.0,
}


@dataclass(frozen=True)
class CircuitBreakerThresholds:
    """Drawdown thresholds for the four state transitions.

    All values are fractions of peak equity, in the closed interval [0, 1].
    Invariants (enforced in __post_init__):
      0 < half_dd < out_dd
      0 ≤ half_to_full_recover_dd < half_dd        (hysteresis around HALF trigger)
      half_to_full_recover_dd ≤ out_to_half_recover_dd < out_dd
                                                   (HALF→FULL requires deeper recovery
                                                    than OUT→HALF — OUT recovers to HALF
                                                    first, then HALF to FULL)
    """
    half_dd: float = 0.08
    out_dd: float = 0.12
    half_to_full_recover_dd: float = 0.05
    out_to_half_recover_dd: float = 0.08

    def __post_init__(self) -> None:
        if not 0 < self.half_dd < self.out_dd < 1:
            raise ValueError(
                f"thresholds must satisfy 0 < half_dd ({self.half_dd}) < "
                f"out_dd ({self.out_dd}) < 1"
            )
        if not 0 <= self.half_to_full_recover_dd < self.half_dd:
            raise ValueError(
                f"half_to_full_recover_dd ({self.half_to_full_recover_dd}) must be "
                f"in [0, half_dd={self.half_dd}) to provide hysteresis"
            )
        if not self.half_to_full_recover_dd <= self.out_to_half_recover_dd < self.out_dd:
            raise ValueError(
                f"out_to_half_recover_dd ({self.out_to_half_recover_dd}) must be in "
                f"[half_to_full_recover_dd={self.half_to_full_recover_dd}, "
                f"out_dd={self.out_dd}) — OUT recovers to HALF first"
            )


@dataclass(frozen=True)
class CircuitBreakerState:
    """Persistent state across days. Callers must thread this through."""
    state: State = "FULL"
    peak_equity: float = 0.0

    def __post_init__(self) -> None:
        if self.state not in VALID_STATES:
            raise ValueError(f"unknown state: {self.state}")
        if self.peak_equity < 0:
            raise ValueError(f"peak_equity must be non-negative, got {self.peak_equity}")


@dataclass(frozen=True)
class CircuitBreakerStep:
    """Result of one step: the new state + diagnostic info for logging."""
    new_state: CircuitBreakerState
    drawdown: float                  # fraction of peak; 0 if at/above peak
    transitioned: bool
    previous_state: State            # state at entry; useful for log entries


def exposure_fraction(state: State) -> float:
    """Fraction of strategy-allocated capital that should be deployed in `state`.

    The remainder sits in cash (SHV in our paper sim). Callers multiply intended
    position sizes by this fraction.
    """
    return EXPOSURE_FRACTION_BY_STATE[state]


def step(
    state: CircuitBreakerState,
    current_equity: float,
    thresholds: CircuitBreakerThresholds,
) -> CircuitBreakerStep:
    """Advance the circuit-breaker by one observation.

    Behaviour:
      - On first call (peak_equity == 0), peak_equity is initialised to current_equity.
      - Peak is updated to max(peak, current_equity) on every call (running maximum).
      - Drawdown is (peak - current) / peak, floored at 0.
      - At most one state transition per call. Adjacent states only:
        FULL ↔ HALF, HALF ↔ OUT. Never FULL → OUT or OUT → FULL in a single step.
    """
    if current_equity < 0:
        raise ValueError(f"current_equity must be non-negative, got {current_equity}")

    new_peak = max(state.peak_equity, current_equity)
    drawdown = (new_peak - current_equity) / new_peak if new_peak > 0 else 0.0

    new_state_name: State = state.state
    if state.state == "FULL" and drawdown >= thresholds.half_dd:
        new_state_name = "HALF"
    elif state.state == "HALF":
        if drawdown >= thresholds.out_dd:
            new_state_name = "OUT"
        elif drawdown <= thresholds.half_to_full_recover_dd:
            new_state_name = "FULL"
    elif state.state == "OUT" and drawdown <= thresholds.out_to_half_recover_dd:
        new_state_name = "HALF"

    transitioned = new_state_name != state.state
    return CircuitBreakerStep(
        new_state=replace(state, state=new_state_name, peak_equity=new_peak),
        drawdown=drawdown,
        transitioned=transitioned,
        previous_state=state.state,
    )


def from_config(circuit_breaker_cfg: dict | None) -> CircuitBreakerThresholds:
    """Build a `CircuitBreakerThresholds` from the `circuit_breaker:` block of
    `config/risk_limits.yaml`.

    Missing block or `enabled: false` returns the chosen-by-backtest defaults so
    callers can always get a valid object. Callers that need to honour `enabled`
    should check it themselves and skip throttling if false.
    """
    cfg = circuit_breaker_cfg or {}
    return CircuitBreakerThresholds(
        half_dd=float(cfg.get("half_dd", 0.08)),
        out_dd=float(cfg.get("out_dd", 0.12)),
        half_to_full_recover_dd=float(cfg.get("half_to_full_recover_dd", 0.05)),
        out_to_half_recover_dd=float(cfg.get("out_to_half_recover_dd", 0.08)),
    )


# ---------------------------------------------------------------------------
# Persistence — for multi-routine continuity in paper trading
# ---------------------------------------------------------------------------
# State lives at trades/paper/circuit_breaker.json. Each routine load → step →
# save. Not append-only (it's a single mutable record, not a log) — hook #12
# only restricts trades/paper/log.csv and decisions/by_symbol/*.md.

def load_state(path: Path | None = None) -> CircuitBreakerState:
    """Load breaker state from disk. Returns the default starting state if no
    file exists yet (first ever run)."""
    p = path or STATE_PATH
    if not p.exists():
        return CircuitBreakerState()
    data = json.loads(p.read_text(encoding="utf-8"))
    return CircuitBreakerState(
        state=data["state"],
        peak_equity=float(data["peak_equity"]),
    )


def save_state(state: CircuitBreakerState, *, path: Path | None = None,
               last_observed_equity: float | None = None) -> None:
    """Persist breaker state. `last_observed_equity` is recorded only as a
    diagnostic for humans reading the file — it is NOT consumed on next load
    (peak_equity is the only state-affecting field).
    """
    p = path or STATE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state.state,
        "peak_equity": state.peak_equity,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if last_observed_equity is not None:
        payload["last_observed_equity"] = last_observed_equity
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def advance(
    current_equity: float,
    thresholds: CircuitBreakerThresholds,
    *,
    path: Path | None = None,
) -> CircuitBreakerStep:
    """Load → step → save in one call. Convenience for routine code.

    Routines call this once per run with today's portfolio equity. If a
    transition occurs, the routine is responsible for writing a
    `logs/risk_events/<ts>_circuit_breaker.md` entry — `advance` itself does
    no logging (keeps this module testable without filesystem side-effects
    beyond the state file).
    """
    state = load_state(path)
    result = step(state, current_equity, thresholds)
    save_state(result.new_state, path=path, last_observed_equity=current_equity)
    return result
