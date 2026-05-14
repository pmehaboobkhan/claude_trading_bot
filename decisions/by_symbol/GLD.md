# GLD — Per-Symbol Decision Log

**Cumulative stats (updated 2026-05-12 EOD):**

- Open paper positions: 1 (qty 34 @ $430.7861, opened 2026-05-12T20:02:25Z)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (latest mark): -$2.93 (close $430.70 vs entry $430.7861)
- Win rate: n/a (no closed trades)
- Active strategies: dual_momentum_taa (primary), gold_permanent_overlay (subsumed)

## 2026-05-12 — PAPER_BUY (dual_momentum_taa)

- Decision file: `decisions/2026-05-12/2000_GLD.json`
- Signal: ENTRY, top-1 risk asset (12m ret +38.56%, above 210d MA)
- Filled: 34 shares @ $430.7861 (quote $430.70 + slippage/half-spread)
- Stop: $387.63, Target: $538.375, R/R: 2.5:1
- Sizing rationale: Strategy A intent was 60%, Strategy C overlay 10%; per-trade risk cap (1.5% / 10% stop) reduced position to 15% of $100k; single line item satisfies both A and C.
- Routine: end_of_day_2026-05-12, mode PAPER_TRADING, cb_state=FULL, throttle=1.0
- Risk Manager: APPROVED. Compliance: APPROVED.

## 2026-05-12 — NO_TRADE (gold_permanent_overlay — subsumed)

- Decision file: `decisions/2026-05-12/2000_GLD_overlay_note.json`
- Rationale: Overlay's 10% allocation is fully covered by Strategy A's 15% GLD position above. No additional shares opened (no double-booking).

## 2026-05-12 — EOD re-run (20:40Z, no trade)

- Routine: end_of_day_2026-05-12 (scheduled 16:30 ET re-run)
- Signal: ENTRY re-confirmed (top-1 in Strategy A; +38.56% 12m; above 210d MA). Strategy C overlay also re-confirms (subsumed).
- Position held; no fill, no close.
- Mark (2026-05-07 bar close): $431.67. Unrealized PnL: +$30.05 (+0.21%).
- cb_state=FULL, throttle=1.0; equity peak $99,992.31 unchanged.

## 2026-05-13 — EOD held (re-confirm ENTRY, no trade)

- Routine: end_of_day_2026-05-13, mode PAPER_TRADING, cb_state=OUT (no transition this run), throttle=0.0.
- Signal: ENTRY re-confirmed for both strategies (dual_momentum_taa top-1; gold_permanent_overlay permanent policy).
- Quote at close $430.55. Mark vs entry $430.7861 → -$8.03 (-0.05%). Stop $387.63 (10.0% headroom).
- Decision: continue holding; no new decision file written (held-position re-confirm; no fill, no close).
- Cumulative: still 1 open position, qty 34 @ $430.7861. Day-1 friction artifact carries forward.

## 2026-05-14 — EOD held (re-confirm ENTRY, no trade)

- Routine: end_of_day_2026-05-14, mode PAPER_TRADING, cb_state=OUT (no transition; 7th consecutive routine on inflated peak), throttle=0.0.
- Signal: ENTRY re-confirmed for both strategies (dual_momentum_taa top-1: 12m +39.53% > SPY +30.88% > IEF +0.54%; gold_permanent_overlay permanent policy).
- Quote at pre_close (19:41Z in-market): $428.01. Post-close IEX last $427.56 (degraded; bid $427.10 / ask $427.56, but quote_ts 20:01Z — kept as reference only).
- Mark vs entry $430.7861 → **-$94.39 (-0.64%)**. Stop $387.63 (9.4% headroom).
- Decision: continue holding; no new decision file written (held-position re-confirm; no fill, no close).

**Cumulative stats (updated 2026-05-14 EOD):**

- Open paper positions: 1 (qty 34 @ $430.7861)
- Closed paper trades: 0
- Realized PnL: $0.00
- Unrealized PnL (mark $428.01): -$94.39 (-0.64%)
- Win rate: n/a (no closed trades)
- Active strategies: dual_momentum_taa (primary), gold_permanent_overlay (subsumed)
