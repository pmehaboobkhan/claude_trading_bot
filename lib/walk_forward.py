"""Pure helpers for walk-forward evaluation.

No network, no I/O, no backtest engine — just window arithmetic and
metric aggregation. The driver script in scripts/run_walk_forward.py
combines these with the backtest engine.
"""
from __future__ import annotations

import math
from datetime import datetime


def add_years(d: str, years: int) -> str:
    """Add an integer number of years to an ISO date string."""
    parsed = datetime.strptime(d, "%Y-%m-%d").date()
    try:
        return parsed.replace(year=parsed.year + years).isoformat()
    except ValueError:
        # Feb 29 → Feb 28 fallback
        return parsed.replace(year=parsed.year + years, day=28).isoformat()


def generate_windows(
    *, full_start: str, full_end: str,
    is_years: int, oos_years: int, step_years: int,
) -> list[tuple[str, str, str, str]]:
    """Generate (is_start, is_end, oos_start, oos_end) windows.

    is_end == oos_start (no gap). Folds whose oos_end > full_end are dropped.
    Returns ISO date strings.
    """
    out: list[tuple[str, str, str, str]] = []
    cur_is_start = full_start
    while True:
        is_end = add_years(cur_is_start, is_years)
        oos_end = add_years(is_end, oos_years)
        if oos_end > full_end:
            break
        out.append((cur_is_start, is_end, is_end, oos_end))
        cur_is_start = add_years(cur_is_start, step_years)
    return out


def select_best(
    candidates: list[dict],
    *,
    by: str = "sharpe",
    max_mdd_pct: float | None = None,
) -> dict:
    """Pick the candidate with the highest `by` metric, subject to a DD cap.

    `candidates` items are {"params": {...}, "metrics": {sharpe, cagr, mdd, ...}}.
    Raises ValueError if no candidate satisfies the constraint.
    """
    eligible = candidates
    if max_mdd_pct is not None:
        eligible = [c for c in candidates if c["metrics"].get("mdd", math.inf) <= max_mdd_pct]
    if not eligible:
        raise ValueError(f"no candidate satisfies max_mdd_pct={max_mdd_pct}")
    return max(eligible, key=lambda c: c["metrics"].get(by, -math.inf))


def aggregate_oos(folds: list[dict]) -> dict:
    """Chain OOS daily returns across folds; report CAGR / MaxDD / Sharpe.

    Each fold dict must have 'oos_daily_returns' (list of float).
    """
    chained: list[float] = []
    for f in folds:
        chained.extend(f["oos_daily_returns"])
    if not chained:
        return {"chained_cagr": 0.0, "chained_mdd": 0.0, "chained_sharpe": 0.0,
                "n_days": 0}

    # Equity curve from chained returns
    equity = [1.0]
    for r in chained:
        equity.append(equity[-1] * (1.0 + r))

    n_days = len(chained)
    years = n_days / 252.0
    chained_cagr = ((equity[-1]) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else 0.0

    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100.0
        if dd > mdd:
            mdd = dd

    if len(chained) > 1:
        mean = sum(chained) / len(chained)
        var = sum((r - mean) ** 2 for r in chained) / (len(chained) - 1)
        std = math.sqrt(var)
        chained_sharpe = (mean / std * math.sqrt(252.0)) if std > 0 else 0.0
    else:
        chained_sharpe = 0.0

    return {
        "chained_cagr": chained_cagr,
        "chained_mdd": mdd,
        "chained_sharpe": chained_sharpe,
        "n_days": n_days,
    }
