# Risk Profile — Calm Turtle

> Ground truth for the operator's risk tolerance and the system's hard limits.
> Update via PR only. Re-sign annually.

## Identity

- Operator: <fill in>
- Account: Alpaca Paper (Phase 4+); Alpaca Live (Phase 8+ only).
- Account type: <cash / margin> — this affects PDT rules, settlement, wash-sale.
- Last reviewed: 2026-05-09.

## Goal (risk-adjusted, not absolute)

Beat **SPY** on a risk-adjusted basis (Sharpe-like, with **max drawdown ≤ SPY's max drawdown**) over rolling 6- and 12-month windows. Secondary check: also beat **equal-weight buy-and-hold of the 11 sector ETFs** — if the system can't beat that, the trading is just adding noise and tax events.

## Capital allocation

- Paper notional: $100,000 (default; adjust to match your Alpaca paper account).
- Live capital allocated for Phase 8+: **TBD**. Default plan: 0 until risk profile is re-signed at Phase 8 transition.

## Loss tolerances (hard ceilings, not targets)

| Window | Limit |
|---|---|
| Daily | $500 OR 0.5% of equity, whichever is tighter. |
| Weekly | 2% of equity. |
| Monthly | 5% of equity. |
| Drawdown trigger for monthly review `HALT_AND_REVIEW` | > 8% peak-to-trough at any time. |

## Permissions

- Long-only equities/ETFs.
- No margin, options, short selling, leveraged ETFs, averaging down. (See `config/risk_limits.yaml > permissions`.)

## Halts

- 3 consecutive losses → 1-day cool-off.
- Daily loss cap breach → halt rest of day.
- Reconciliation discrepancy → halt until manual reconcile.

## Promotion criteria (research → paper → proposals → live)

| Transition | Required evidence |
|---|---|
| Research-only → Paper trading | Phase 1+2+3 complete; 4 weeks clean research routines. |
| Paper trading → Live proposals | ≥ 60 paper-trading days; ≥ 50 paper trades; beats both benchmarks risk-adjusted on 6-month basis; drawdown ≤ SPY's. |
| Live proposals → Live execution (per-trade approval) | 30 days of clean live proposals (zero limit breaches); explicit human PR + signed update to this doc. |
| Live execution (per-trade approval) → autonomous live | **Default: never.** Requires explicit, deliberate decision after months of evidence. |

## Tax considerations

- This system does NOT optimize for taxes. Wash-sale rules apply on live trading.
- Annual export of `trades/paper/log.csv` (or live equivalent) for accountant.
- Verify with a CPA before going live.

## Rotation history

| Date | What rotated | Why |
|---|---|---|
| 2026-05-09 | Initial profile created | Phase 0 |

## Sign-off

- Last signed: <pending>
- Signed by: <pending>
