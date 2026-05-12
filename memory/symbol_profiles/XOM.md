# Symbol Profile — XOM

Descriptive observations only. No buy/sell recommendations.

## Identity
- Ticker: XOM (Exxon Mobil)
- Asset class: US large-cap equity (energy / integrated oil & gas)
- Approved in `config/watchlist.yaml` for paper trading (per project state context)

## Role in strategy mix
- **Strategy B — `large_cap_momentum_top5` (30% capital):** member of the 20-mega-cap universe.

## Today's signal (2026-05-12)
- Signal: ENTRY, `large_cap_momentum_top5`, **rank 2**, 6m return **+33.58%**.
- Source: `journals/daily/2026-05-12.md` line 9.

## Known characteristics
- XOM is a commodity-sensitive name; its 6m momentum reading is partly a function of crude oil price action over the same window.
- Strategy B treats it identically to other mega-caps for ranking purposes — no sector-specific weighting in v1.

## Known risks / flags
- **Sector concentration risk:** if Strategy B's top-5 ends up heavy in energy or commodity-correlated names, the resulting sleeve will be less diversified than a 5-stock count implies. Worth observing as the portfolio fills.
- **News connector offline** — no read on company-specific announcements.
- Data staleness: latest bar 2026-04-23.

## Observation log
- 2026-05-12: surfaced at rank 2 of Strategy B's top-5; no position opened.

## Open questions for future review
1. Realized forward return vs the rank-2 momentum prediction.
2. Co-movement with other commodity-sensitive names in the watchlist (sector-correlation observation, not a basis for action).

## Sources
- `journals/daily/2026-05-12.md`
