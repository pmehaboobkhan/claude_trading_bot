# Proposed update — Option B: Market-On-Close execution for the EOD entry/exit decision

**Author:** Claude (assistant)
**Date:** 2026-05-15
**Status:** **SUPERSEDED 2026-05-16 by PR #20** (Alpaca-authoritative mirror). The operator runs no quant validation loop and wants the real Alpaca paper account live with a simple uniform model. MOC two-phase execution is not being pursued. Retained for historical record only.
**Reason:** Operator wants real Alpaca paper-mirror trading. Investigation found that flipping `BROKER_PAPER=alpaca` under the current schedule does not produce clean paper fills — it produces a daily mirror-divergence halt — because the only routine that opens positions runs *after* the regular-session close.

## Problem statement (verified)

- US regular session closes **16:00 ET**. `end_of_day` cron is `30 16 * * 1-5` = **16:30 ET** (`config/routine_schedule.yaml`). The routine *must* run after the close because all three strategies (`dual_momentum_taa`, `large_cap_momentum_top5`, `gold_permanent_overlay`) compute signals from the **official daily close** + long lookbacks.
- With `BROKER_PAPER=alpaca`, `lib/paper_sim.py:_alpaca_submit_and_wait` submits a `time_in_force="day"` **market** order (`lib/broker.py:submit_market_order`), polls **5 s** (`ALPACA_FILL_POLL_SECONDS = 5.0`), and **does not cancel the order on timeout** (`lib/paper_sim.py:88`).
- A DAY market order submitted at 16:30 ET cannot fill in that 5 s window (market closed; market orders are not extended-hours eligible). The poll times out, local state records the **sim price (today's close)**, but a **live order is left resting at Alpaca** and fills at the next session's open at a different price.
- `end_of_day` step 8a reconciliation then detects the local-vs-Alpaca mismatch and fires an **URGENT mirror-divergence alert + halt-progression**, requiring an operator `--reset-fresh-start`. This recurs on every entry.
- The internal sim (`BROKER_PAPER=sim`) does **not** have this problem: it fills at `quote_price=<today_close>`, which **exactly matches the backtest fill model** (`lib/backtest.py:185-198` and `:170-171` — entries and strategy exits fill at `bars[-1]["close"]`). The 8–10% return / Sharpe / max-DD targets were all validated on close fills.

**Conclusion:** sim mode is methodologically consistent with the backtested strategy; Alpaca-mirror mode at the 16:30 cron is not. The fix must make the broker fill land at the **official close** (so live ≡ backtest), not move the strategy intraday.

## Proposed change — two-phase MOC execution

Split the EOD strategy decision into two phases. Strategy entries **and strategy exits** (the EOD signal-driven ones) are submitted as **Market-On-Close (MOC)** orders before Alpaca's MOC cutoff, so they fill in the official 16:00 closing auction — the same price the backtest assumes.

| Phase | Time (ET) | Responsibility |
|---|---|---|
| **Phase 1 — submit** | ~15:50 (well before Alpaca's ≈15:59 MOC cutoff; earlier on half-days) | Deterministic signal eval, consolidation, circuit-breaker throttle, risk + compliance gates, write decision files, submit MOC orders for approved entries/exits. **No fill is known yet.** |
| **Phase 2 — confirm** | 16:30 (existing `end_of_day` slot) | Poll the MOC orders for actual closing-auction fill price, write fills to `log.csv` / `positions.json`, run step 8a reconciliation against now-known fills, journal, commit, notify. Also handles intraday risk-exit follow-ups as today. |

Intraday **risk-driven** exits (stop/target/news/daily-loss in `market_open` / `midday` / `pre_close`) are **unchanged** — those are immediate market orders during regular hours (they fill in the existing 5 s window) and are intentionally not backtest-fill-matched because they are risk events, not strategy signals.

### Why MOC (Option B) over re-baselining to next-open (Option A)

The backtest already fills at the close. MOC fills at the close. So **the existing performance validation stays valid** — no backtest re-baselining, no re-derivation of the 8–10%/Sharpe/DD targets. The *only* new approximation introduced is **signal timing**: Phase 1 computes signals at ~15:50 using the latest available price as a close proxy, whereas the backtest uses the true 16:00 close. That approximation must be quantified before adoption (see Validation gate).

## Affected files (all PR-locked or strategy-affecting — this proposal does not change them)

| File | Lock | Change described |
|---|---|---|
| `config/routine_schedule.yaml` | PR-only | Add a Phase-1 entry-submission routine at ~15:50 ET (trading-day + half-day aware). Keep `end_of_day` 16:30 as Phase-2 confirm/reconcile/journal. |
| `prompts/routines/end_of_day.md` | PR-only | Split: move signal eval + CB + gates + MOC submission to Phase 1; keep reconcile/journal/commit/notify + fill confirmation in Phase 2. Step 7/6 calls submit MOC instead of immediate market. |
| New `prompts/routines/end_of_day_submit.md` (or equivalent) | PR-only | Phase-1 spec. Draft to be authored as part of the PR. |
| `lib/broker.py` | tests-gated | Support MOC time-in-force (Alpaca `TimeInForce.CLS`). Add an explicit `submit_moc_order` or extend `submit_market_order`. |
| `lib/paper_sim.py` | tests-gated | New async path: on MOC submit do **not** fall back to sim price; record status `PENDING_MOC` + broker order id + decision link. Add a `confirm_moc_fills()` used by Phase 2 that polls `get_order`, writes the real fill, and feeds reconciliation. |
| `lib/backtest.py` | tests-gated | No fill-model change. Add a **signal-timing sensitivity** variant (signal computed on a T-minus-N-minute price, fill still at close) for the validation gate. |
| `docs/operator_runbook.md` | writable | Update the BROKER_PAPER enablement section: enablement now requires this two-phase flow; document the half-day cutoff behaviour. |

## Design details to resolve in the PR

1. **Circuit-breaker timing.** The CB throttle gates *entries*, so the CB consultation + throttle computation must happen in Phase 1 (15:50), before MOC submission — using 15:50 equity as the proxy. CB peak-tracking / transition logging can stay in Phase 2. Document the equity-timing proxy.
2. **Async MOC fill.** A MOC submitted at 15:50 fills ~16:00. `_alpaca_submit_and_wait`'s 5 s synchronous poll is incompatible — Phase 1 must record `PENDING_MOC` and **not** write a fill price; Phase 2 polls for the realized auction price. `positions.json` reflects the real MOC fill, not a proxy.
3. **Idempotency / no double-submit.** Phase 2 must NEVER re-open positions — it only confirms Phase-1 submissions. Continue deriving `client_order_id` from `decisions/<date>/<HHMM>_<sym>.json` so a Phase-1 retry can't double-fill.
4. **Half-days / holidays.** Alpaca's MOC cutoff shifts on early-close days (13:00 ET close). The Phase-1 cron + a proper trading calendar must skip non-trading days and submit before the *shifted* cutoff. The crude holiday list in `.github/workflows/eod_watchdog.yml` is insufficient — use a real calendar.
5. **MOC rejection handling.** If a MOC order is rejected (submitted past cutoff, symbol not MOC-eligible, etc.), the decision must record `REJECTED, reason=moc_rejected`, NOT silently fall back to a synthetic fill. A rejected entry is a NO_TRADE for that symbol that day — log it; do not improvise.
6. **alpaca-py support check.** Verify `TimeInForce.CLS` exists in the pinned alpaca-py (0.43.4) and that the paper sandbox honours MOC. If not, this proposal is blocked on a dependency bump (separate PR).

## Validation gate (MUST pass before adoption)

Run a backtest sensitivity analysis: **canonical** (signal@16:00 close, fill@close) vs **proposed-live proxy** (signal@~15:50 price, fill@close), over the full validated window and the 2008-inclusive stress window.

Acceptance criteria (tune in PR; suggested starting bar):
- Annualized-return delta within a small tolerance (e.g. ≤ ~25 bps).
- Sharpe delta ≤ ~0.05.
- No new max-drawdown breach of the 12% action threshold or 15% cap.
- No change in any monthly halt-trigger outcome.

If the 15:50-proxy materially changes results, **Option B is rejected** and we revisit Option A (model next-open fills + full backtest re-baseline) or keep sim-only indefinitely.

## Interim guidance (until this lands)

- Keep **`BROKER_PAPER=sim`**. It is genuine paper trading, close-accurate, and the only configuration consistent with the backtested strategy.
- Do **not** set `BROKER_PAPER=alpaca` at the current 16:30 cron — it will divergence-halt on the first entry.
- The data-feed + `calm_turtle` repo-binding validation (Run now on `end_of_day`) is still valid and worth doing in sim mode.

## Open questions for the human reviewer

1. New Phase-1 routine vs. re-timing the existing `end_of_day` to 15:50 and adding a thin 16:30 confirm step — which is cleaner operationally?
2. Acceptance tolerances for the validation gate.
3. Should strategy *exits* also be MOC (proposed: yes, for backtest symmetry), or only entries?
4. Is a one-session signal/fill realism gap acceptable for the live-gate evidence, or do we want Option A's exact-consistency instead?
