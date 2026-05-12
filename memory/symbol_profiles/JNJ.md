# Symbol Profile — JNJ

Descriptive observations only. No buy/sell recommendations.

## Identity
- Ticker: JNJ (Johnson & Johnson)
- Asset class: US large-cap equity (healthcare / pharma + medical devices)
- Approved in `config/watchlist.yaml` for paper trading (per project state context)

## Role in strategy mix
- **Strategy B — `large_cap_momentum_top5` (30% capital):** member of the 20-mega-cap universe.

## Today's signal (2026-05-12)
- Signal: ENTRY, `large_cap_momentum_top5`, **rank 5 (listed as alternate)**, 6m return **+20.17%**.
- Source: `journals/daily/2026-05-12.md` lines 9 and 11.

## Known characteristics
- Healthcare-defensive profile; second lowest momentum reading among ENTRY-tagged Strategy B candidates today.
- The pre-market report flags JNJ as alternate (journal line 11), suggesting it sits at the edge of the top-5 vs the hold-zone names AMZN (+14.87%) and NVDA (+10.24%).

## Known risks / flags
- **News connector offline** — pharma names are particularly exposed to regulatory, trial-outcome, and litigation news; silence here is a risk factor.
- Data staleness: latest bar 2026-04-23.
- **Borderline rank:** with only ~5 percentage points separating rank 5 from rank 6 (AMZN), small input changes could move JNJ in or out of the top-5 in subsequent days. Worth observing whether borderline names cycle in/out frequently — if so, transaction-cost drag becomes a concern at the strategy level.

## Observation log
- 2026-05-12: surfaced at rank 5 of Strategy B's top-5 (alternate); no position opened.

## Open questions for future review
1. Realized forward return vs the rank-5 momentum prediction.
2. Frequency of rank-5 / rank-6 swaps over the next 20 trading days — proxy for top-5 churn.

## Sources
- `journals/daily/2026-05-12.md`
