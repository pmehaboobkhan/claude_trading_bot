# Strategy B re-validation under realistic execution (next-open) — 2026-05-16

**Path (a)** from the MOC gate analysis: the MOC signal-proxy gate FAILED
because `large_cap_momentum_top5`'s rank-by-~126d-return needs the *exact*
official close (so it cannot fill at that close via MOC). This re-baselines
strategy B under realistic execution — **signal from close[D], fill at
open[D+1]** — and checks whether its edge survives, or was an artifact of the
backtest filling at the same close it computed the signal from.

## Method

- `lib.backtest.run_backtest` gained `fill_timing` (default `"close"` —
  **bit-for-bit identical** to the prior engine; the canonical baseline
  reproduces exactly, see parity row below). `"next_open"` fills ENTRY/EXIT
  at the next bar's open; signal logic unchanged; no next bar → falls back to
  close[D] (no invented lookahead). TDD'd (`tests/test_backtest_fill_timing.py`).
- `--strategy-b-fill {close,next_open}` (default `close`) is passed **only**
  to strategy B's `run_backtest` call. Strategy A (`dual_momentum_taa`) and C
  (`gold_permanent_overlay`) are untouched — they fill at the close, which is
  valid for them (the gate showed zero divergences for A/C → MOC@close works).
- Canonical window: `--start 2013-05-24 --end 2026-05-08 --circuit-breaker`,
  modern universe.

## Results

| Metric | Baseline (close) | B = next_open | Δ |
|---|---|---|---|
| Annualized return | +10.60% | **+10.14%** | −0.46 pp |
| Max drawdown | 12.58% | **12.45%** | −0.13 pp (better) |
| Sharpe (rough) | 1.10 | **1.05** | −0.05 |
| Strategy B standalone | +1534.41% | +1346.57% | −187.84 pp |
| Strategy A contribution | $162,604.09 | $162,604.09 | **0 (identical)** |
| Strategy C contribution | $35,568.33 | $35,568.33 | **0 (identical)** |
| CLAUDE.md target eval | PASS | **PASS** | — |

Baseline parity: the `close` run reproduces the canonical +10.60% / 12.58% /
1.10 — the refactor introduced no drift. A and C contributions are
bit-identical across runs, empirically confirming the change is isolated to
strategy B.

## Verdict

**Strategy B's edge survives realistic next-open execution.** Under honest
execution the portfolio still meets every CLAUDE.md absolute target
(annualized ≥10%, max DD ≤15%, Sharpe ≥0.8): **+10.14% / 12.45% / 1.05,
OVERALL PASS**. The momentum edge was *not* an artifact of the backtest
filling at the same close it ranked on — it costs a modest haircut
(−0.46 pp annualized; B standalone +1534%→+1347%) and clears the bar.

Option B (path a) is **viable**.

## Caveats / remaining before any go-live

1. **Survivor-universe robustness not re-checked.** The `as_of`
   survivor-bias-stress path was deliberately left at close-fill (scope
   boundary; it is a separate stress test, not the canonical validator).
   Recommend re-running `--strategy-b-universe-mode as_of --strategy-b-fill
   next_open` before final sign-off, to confirm B's edge is neither
   survivor-biased *nor* execution-fragile.
2. **Tolerance is a human call.** −0.46 pp annualized exceeds the ~25 bps
   heuristic floated in the MOC proposal, but all binding CLAUDE.md targets
   pass with margin and Sharpe stays >1.0. Quant sign-off on accepting the
   haircut is required — this report does not self-approve.
3. **This re-validates the backtest only — it does NOT enable Option B.**
   The live architecture is now necessarily **per-strategy**: A & C →
   MOC at the close (validated, signal-proxy fine); **B → signal at the
   official close (post-16:00), market order filling at the next open**.
   That per-strategy execution split, the routine/schedule wiring, and a
   human PR of the PR-locked files are all still required. `BROKER_PAPER=sim`
   remains the correct interim.

## Recommended next steps

1. Robustness: `as_of` universe × `next_open` (caveat 1).
2. Quant sign-off on the haircut (caveat 2).
3. Design the per-strategy live execution wiring (A/C MOC@close; B
   close-signal + next-open fill) as a PR-locked proposal — human PR.
