# Strategy B robustness: survivor-bias × execution (2×2) — 2026-05-16

Caveat (1) from the next-open re-validation memo: confirm strategy B's edge
is **neither survivor-biased nor execution-fragile, together**. This stacks
both honest corrections — point-in-time `as_of` universe AND realistic
`next_open` execution — and reports the full 2×2.

`fill_timing` was threaded into `run_strategy_b_as_of` (reuses the tested
`lib.backtest._fill_quote`; default `"close"` unchanged). A and C are
untouched in every cell (contributions bit-identical: A $162,604.09,
C $35,568.33 across all four runs).

Window `2013-05-24..2026-05-08 --circuit-breaker`.

## 2×2 portfolio results

| Universe \ Fill | close | next_open |
|---|---|---|
| **modern** | +10.60% / DD 12.58% / Sharpe 1.10 — PASS (both targets) | +10.14% / 12.45% / 1.05 — PASS (both) |
| **as_of** (survivor-corrected) | +9.13% / 12.57% / 0.97 — PASS (low target; high FAIL) | +10.01% / 13.00% / 1.02 — PASS (both) |

B standalone: modern 1534%→1347% (close→next_open); as_of 2013%→1706%.

**Every cell is OVERALL PASS** (meets the minimum CLAUDE.md bar: annualized
≥8%, max DD ≤15%, Sharpe ≥0.8). The worst cell — survivor-corrected with
same-close fills — still clears the minimum (9.13% / 0.97). Under *both*
honest corrections stacked, the portfolio passes both the low and high
targets (10.01% / 13.00% / 1.02).

## Honest flag — counterintuitive direction

In the **modern** universe, next_open is slightly *worse* than close
(−0.46 pp) — the intuitive friction direction. In the **as_of** universe,
next_open is slightly *better* than close (+0.88 pp). Execution friction is
not strictly return-reducing for a momentum strategy (buying the next open
after a strong close can capture or miss continuation depending on the
universe/path), so a sign flip across universes is plausible — but the
**magnitude asymmetry** (−0.46 vs +0.88 pp) means B's result is more
path-/execution-sensitive than a clean "friction always costs X" model.

Checked for lookahead: the signal uses bars ≤ i (close[i]); the fill uses
bar i+1's open, which feeds no decision — correct next-open semantics, no
lookahead. The asymmetry is a real path-sensitivity, not a bug.

## Verdict

**Robustness check passes.** B's edge survives survivor-bias correction and
realistic execution independently and stacked; the portfolio clears minimum
targets in all four cells and the full targets under both stacked
corrections. Path (a) holds up.

**Not a clean "ship it".** The execution-direction asymmetry warrants a
per-trade attribution (why next_open helps as_of but hurts modern) before
live sign-off — it's the kind of thing that, unexamined, becomes a
post-hoc rationalization. Recommended, not blocking.

## Status / remaining (unchanged from prior memo + this)

1. ~~as_of × next_open robustness~~ — done (this report).
2. Quant sign-off: accept the next-open haircut (modern −0.46 pp) AND the
   execution-direction asymmetry, or commission the attribution first.
3. Per-strategy live execution wiring (A/C MOC@close; B close-signal +
   next-open market fill) as a PR-locked proposal — human PR.

`BROKER_PAPER=sim` remains the validated interim throughout.
