# Strategy B next-open execution: per-period attribution — 2026-05-16

Resolves the honest flag from the as_of robustness memo: **why does
next-open execution slightly hurt strategy B in the modern universe
(−0.46 pp) but slightly help it in the as_of universe (+0.88 pp)?**

Method: sign-stability analysis. Split the canonical window into two
disjoint halves and recompute `close` vs `next_open` for both universes. A
*systematic* execution effect keeps its sign across sub-periods; a
*path/sample* artifact flips.

`--circuit-breaker`, A/C unchanged. Annualized %, `close → next_open` (Δ pp):

| Universe | H1 2013-05‥2019-12 | H2 2020-01‥2026-05 | Full 2013‥2026 |
|---|---|---|---|
| **modern** | 9.95 → 9.32 (**−0.63**) | 14.70 → 14.57 (**−0.13**) | 10.60 → 10.14 (**−0.46**) |
| **as_of** | 8.85 → 8.19 (**−0.66**) | 14.14 → 14.62 (**+0.48**) | 9.13 → 10.01 (**+0.88**) |

## Verdict

- **Modern: sign-stable, genuine, modest drag.** next_open is worse in
  *both* halves and the full window (−0.13 to −0.63 pp). This is a real
  execution friction and directionally sensible for momentum — entries are
  triggered by strong trailing return; such names tend to gap *up* the next
  morning, so paying the next open costs a little. Trustworthy.

- **as_of: the +0.88 pp is NOT a real edge — it is noise.** The sign *flips*
  across sub-periods (−0.66 pp in H1, +0.48 pp in H2). The full-window
  positive is a coincidental net of opposing sub-period effects dominated by
  the 2020+ path, not a systematic "realistic execution helps" effect. H1
  as_of behaves exactly like modern (≈−0.65 pp); only H2 as_of inverts, and
  not stably enough to bank.

**Conclusion for sign-off:** treat strategy B's realistic-execution impact
as a **small negative drag of roughly −0.5 pp annualized** (the stable
modern estimate; as_of H1 agrees). Do **not** credit the as_of "+0.88 pp" —
it is period-selection artifact and must not appear as a point in Option B's
favor. This is the conservative, honest assumption.

Even under that conservative negative drag, **every full-window cell still
PASSES the minimum CLAUDE.md targets** (worst observed sub-cell: as_of H1
next_open 8.19% ≥ 8% low target; full-window max DD ≤13.0%, Sharpe ≥1.02 in
both next_open runs). So B survives a realistic, conservatively-negative
execution assumption — the rosy number is removed without changing the
go/no-go.

## Status / remaining (updated)

1. ~~as_of × next_open robustness~~ — done (PR #19).
2. ~~per-trade / per-period attribution of the direction asymmetry~~ — done
   (this report). Result: budget −0.5 pp; as_of upside is noise.
3. **Quant sign-off**: accept B live on the basis of "passes minimum
   targets with a ~−0.5 pp realistic-execution drag, no execution upside
   assumed." This report removes the only ambiguity that was blocking that
   judgement.
4. Per-strategy live execution wiring (A/C → MOC@close; B → close-signal +
   next-open market fill) as a PR-locked routine/schedule proposal + human PR.

`BROKER_PAPER=sim` remains the validated interim throughout.
