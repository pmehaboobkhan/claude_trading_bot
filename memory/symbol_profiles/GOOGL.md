# Symbol Profile — GOOGL

Descriptive observations only. No buy/sell recommendations.

## Identity
- Ticker: GOOGL (Alphabet Class A)
- Asset class: US large-cap equity (mega-cap)
- Approved in `config/watchlist.yaml` for paper trading (per project state context)

## Role in strategy mix
- **Strategy B — `large_cap_momentum_top5` (30% capital):** member of the 20-mega-cap universe; eligible to be one of the top-5 by 6m return when SPY trend filter is satisfied.

## Today's signal (2026-05-12)
- Signal: ENTRY, `large_cap_momentum_top5`, **rank 1**, 6m return **+35.31%**.
- Source: `journals/daily/2026-05-12.md` line 9.

## Known characteristics (from prior backtest / pivot reports)
- Strategy B's backtest is heavily survivor-biased: today's mega-caps were used as the universe historically, so backtested returns are likely roughly double the realistic forward expectation (per `reports/learning/pivot_validation_2026-05-10.md`).
- The strategy carries a SPY trend filter — entries require SPY above its trend reference. SPY is +4.71% above its 50d MA today (journal line 8), so the filter is satisfied for paper context.

## Known risks / flags
- **Survivor bias** in backtested return expectation (project-level, not symbol-specific).
- **News connector offline** (v1 limitation, journal line 15) → name-specific news events (regulatory action, earnings revisions, etc.) are not observable to the system today; this is treated as a risk factor, not as bullish silence.
- Data staleness: latest bar 2026-04-23. 6m momentum input tolerates this; an EOD same-day staleness re-check is required before opening.

## Observation log
- 2026-05-12: surfaced at rank 1 of Strategy B's top-5; no position opened (pre-market is research-only).

## Open questions for future review
1. How does GOOGL's realized 5d / 20d return compare to the rank-1 momentum prediction?
2. When the news connector comes online, are there material name-specific events in the lookback window that would have changed the read?

## Sources
- `journals/daily/2026-05-12.md`
- `reports/learning/pivot_validation_2026-05-10.md`
