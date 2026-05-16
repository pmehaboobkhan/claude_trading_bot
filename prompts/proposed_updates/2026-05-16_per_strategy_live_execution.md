# Proposed update — Per-strategy live execution wiring (A/C MOC@close · B close-signal + next-open)

**Author:** Claude (assistant)
**Date:** 2026-05-16
**Status:** DRAFT — awaiting human PR review. **Supersedes** `2026-05-15_moc_close_execution.md` (its uniform-MOC assumption was invalidated by the signal-proxy gate for strategy B).
**Do NOT** set `BROKER_PAPER=alpaca` until this lands + quant sign-off + a market-day dry-run.

## Why this supersedes the original MOC proposal

The original proposal assumed a single MOC execution model for all strategies. The signal-proxy validation gate (PR #17) then proved that is wrong for one strategy:

- **A `dual_momentum_taa` (60%) + C `gold_permanent_overlay` (10%)** — gate showed **zero** decision divergence at a ~15:50 proxy over 60 days. MOC@close is valid for them.
- **B `large_cap_momentum_top5` (30%)** — gate **FAILED** (0.8667): its rank-by-~126-day-return needs the *exact official close*, so it can neither use a 15:50 proxy nor fill at that close via MOC. PR #18 re-baselined B under realistic **next-open** execution (portfolio still PASS); PR #19 + the attribution memo set the carry-forward assumption: **budget B at ≈ −0.5 pp annualized realistic-execution drag, credit no upside** (the as_of "+0.88 pp" is period-selection noise).

Execution is therefore necessarily **per-strategy**.

## Proposed architecture

| Strategy | Signal computed | Order | Fill | Submit / confirm |
|---|---|---|---|---|
| A, C | ~15:50 ET (proxy close — gate-clean) | Market-On-Close (`TimeInForce.CLS`) | official 16:00 auction | **Phase-1** ~15:50 submit → **Phase-2** 16:30 `end_of_day` confirm |
| B | **16:30 ET from the official close** (unchanged) | next-open market order | next session's open | submit at 16:30 → **confirm next `market_open` 09:35** |

- **Phase-1 (~15:50 ET, new routine):** A/C only. Deterministic eval + `lib.signal_consolidator` + circuit-breaker throttle + risk + compliance, then `lib.paper_sim.submit_moc_entry` / a new `submit_moc_exit` (→ `lib.broker.submit_moc_order`, already merged in PR #16). Writes `PENDING_MOC` breadcrumbs; positions.json untouched until confirmed. Must run before the exchange MOC cutoff (≈15:59 ET; earlier on half-days).
- **Phase-2 (16:30 ET, existing `end_of_day`):** (a) `lib.paper_sim.confirm_moc_fills()` resolves A/C `PENDING_MOC` → `OPEN` at the real auction price; steps 8/8a reconcile; journal/commit as today. (b) Compute **B**'s signal from the now-final official close (today's step 4 logic, B only), submit B ENTRY/EXIT as next-open market orders recorded `PENDING_NEXT_OPEN` (no synthetic close fallback — that legacy `open_position` 5 s-poll-then-sim behavior is the exact bug to avoid for B).
- **Phase-3 (next `market_open` 09:35 ET):** new `confirm_next_open_fills()` resolves B's `PENDING_NEXT_OPEN` → `OPEN`/`CLOSED` at the realized opening fill; reconcile. `market_open` is already monitoring-only and runs daily — it gains one B-confirmation step (it must NOT open new positions, unchanged).

Intraday risk-driven exits (stop/target/news/daily-loss in market_open/midday/pre_close) are **unchanged** — immediate market orders during regular hours; they are risk events, not strategy signals, and intentionally not backtest-fill-matched.

## Affected files (PR-locked or strategy-affecting — this proposal changes none of them)

| File | Lock | Change described |
|---|---|---|
| `config/routine_schedule.yaml` | PR-only | add Phase-1 A/C-submit routine ~15:50 ET (trading-day + half-day aware); annotate `end_of_day` (Phase-2 + B-submit) and `market_open` (Phase-3 B-confirm) roles |
| New `prompts/routines/<phase1_ac_submit>.md` | PR-only | Phase-1 spec (A/C MOC submission only) — draft authored in the PR |
| `prompts/routines/end_of_day.md` | PR-only | split: A/C = confirm MOC fills; B = compute-from-close + submit next-open; remove the single same-close fill assumption |
| `prompts/routines/market_open.md` | PR-only | add B `confirm_next_open_fills` step (still no new positions) |
| `docs/operator_runbook.md` | writable | per-strategy enablement + half-day cutoff walkthrough |

## Code deltas (non-locked; build via TDD on a `review/*` branch AFTER this is accepted)

- `lib.paper_sim.submit_moc_exit` — A/C EXIT analog of the merged `submit_moc_entry` (entry-only today).
- `lib.paper_sim.submit_next_open_entry` / `submit_next_open_exit` + `confirm_next_open_fills()` — B's queued next-open submit + next-session confirm, mirroring the `PENDING_MOC`/`confirm_moc_fills` pattern (PR #16). **No synthetic close fallback.**
- Strategy-routing guard: A/C may only use the MOC path; B may only use the next-open path (assert, fail loud).
- Trading-calendar / half-day MOC-cutoff awareness (carried from the original proposal's open item; the `eod_watchdog.yml` holiday list is insufficient).
- Idempotency: `client_order_id` derived from the decision file (existing pattern); Phase-2/3 confirmers skip already-finalized order ids (the `confirm_moc_fills` idempotency pattern).

## Validation status

- **A/C MOC@close** — signal-proxy gate clean (PR #17). Validated for the proxy.
- **B next-open** — backtest re-validated (PR #18), robustness 2×2 all PASS (PR #19), attribution done: budget −0.5 pp, no upside; all cells still pass minimum CLAUDE.md targets under that assumption.
- **Remaining before go-live:** (1) quant sign-off on the architecture + the −0.5 pp B drag; (2) a single-trading-day end-to-end dry-run in `BROKER_PAPER=alpaca` (verify A/C MOC fills + B next-open confirm + reconciliation, no divergence-halt); (3) human PR of the locked wiring above.

## Interim guidance

`BROKER_PAPER=sim` only. Sim fills at the close — backtest-consistent for **all three** strategies and the validated paper engine until every item above lands. Nothing here is enabled; the merged primitives (#16) remain dormant.

## Open questions for the human reviewer

1. B Phase-3 confirm location: next `market_open` (09:35, proposed) vs a dedicated next-morning B-confirm routine vs deferring to next `end_of_day` (a full extra day of unconfirmed local state)?
2. Phase-1 (~15:50 A/C): a new routine, or extend `pre_close` (15:30, currently monitoring-only, PR-locked)?
3. Accept the operational split (two submit times, two confirm times) vs a simpler less-accurate single-run model?
4. Half-day MOC-cutoff: which trading-calendar source to standardize on?
5. Does the −0.5 pp B realistic-execution drag (no upside credited) clear your bar to proceed, or do you want B sim-only and only A/C on Alpaca-mirror first?
