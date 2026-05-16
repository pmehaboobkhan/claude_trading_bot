# Option B validation gate — root-cause analysis (2026-05-16)

**Companion to** `moc_signal_proxy_validation_2026-05-16.md` (raw gate output,
5m bars, 15:50 ET cutoff, 60-day sample).

## Verdict: FAIL — and it is a REAL signal sensitivity, not a harness artifact

- Decision-agreement rate **0.8667** vs the 0.99 threshold (52/60 days).
- **Every action divergence is in `large_cap_momentum_top5`.**
  `dual_momentum_taa` and `gold_permanent_overlay` had **zero** action
  divergences across all 60 days — they are effectively validated for Option
  B, exactly as the analytical bound predicted (SMA-sign / permanent
  allocation are immune to a sub-percent last-bar move).

## Artifact ruled out (evidence)

Concern: the close-arm's last bar comes from the daily yfinance series while
the proxy-arm's comes from the intraday series — a daily-vs-intraday
adjustment seam would reshuffle a rank-by-return strategy spuriously.

Checked CSCO on a divergent day (2026-04-02):
- `lib.data` daily close vs yfinance intraday end-of-day price: **0.0000
  (0.000%)** — the two sources agree exactly at the close. No seam.
- 15:50 price vs 16:00 close: **−0.18%** — a normal late-session move.

So the divergence is a genuine price difference, not a data-source artifact.

## Tightening the cutoff does NOT rescue it

| Cutoff (ET) | Agreement | large_cap divergences |
|---|---|---|
| 15:30 (30m bar) | 0.8667 | 19 |
| 15:50 (5m)      | 0.8667 | 14 |
| 15:55 (5m)      | 0.8667 | 19 |
| 15:58 (5m)      | 0.8667 | 19 |

Even reading 1–2 minutes before the close still disagrees with the
exact-close top-5 ranking on ~23–32% of days. `large_cap_momentum_top5`'s
cross-sectional rank-by-~126-day-return cutoff is knife-edge for enough
symbols that **only the exact official close reproduces the backtested
membership**. A near-close proxy does not help.

## Regime-label flips (3–4 days): low severity

`detect_regime` is documented as narrative context, not load-bearing for
entry/exit (the strategies use their own SPY-vs-MA filters). These flips do
not by themselves change trades; noted for completeness, not a blocker on
their own.

## Conclusion

**Option B as specified (15:50 signal + MOC) does NOT preserve the validated
behavior of `large_cap_momentum_top5` — 30% of portfolio capital.** It is
clean for `dual_momentum_taa` (60%) and `gold_permanent_overlay` (10%).

**Do not enable Option B.** `BROKER_PAPER=sim` remains the only configuration
that is backtest-consistent for all three strategies (sim fills at the
close). The gate did exactly its job: it blocked a go-live that would have
corrupted 30% of the paper-trading evidence.

## Options (human / quant decision — not auto-decided)

1. **Re-baseline strategy B under realistic execution** (signal+fill modeled
   consistently — e.g. next-open, or 15:50-signal+MOC modeled) and
   re-validate its 30%-allocation Sharpe/return. This is the original
   "Option A" scoped to strategy B. Substantial; the honest path if B must
   eventually trade live. **Recommended.**
2. **Mixed mode:** MOC for A & C only; keep B sim-only. B's live paper
   evidence stays sim-sourced. Operationally messier; B never gets real
   broker fills.
3. **Borderline deep-dive:** extend the harness to measure each flip's
   distance from the top-5 cutoff and net P&L impact; if all flips are
   negligible knife-edges the operator *may* judge B tolerable. Treat with
   skepticism — "the flips are tiny" is the canonical retail-quant
   rationalization; requires explicit human sign-off.

## Status

Option B: **HOLD.** Nothing changes for the near term — sim mode is correct
and Monday-ready. No PR-locked routine/schedule wiring should proceed until a
path above is chosen and re-validated.
