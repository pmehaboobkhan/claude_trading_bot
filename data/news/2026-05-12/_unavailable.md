# News & Sentiment — 2026-05-12 pre-market

**Status:** `news_unavailable` for all watchlist symbols.

## Reason
v1 has no live news connector wired up (no SEC EDGAR / RSS / WebSearch result cache for this routine run). Per `CLAUDE.md` "Handling missing data":

> News connector down -> mark symbols `news_unavailable`; treat as risk factor, not as "no news = bullish."

## Impact on this routine
- All ENTRY candidates carry an implicit "no news verification" risk factor.
- Sentiment tone for every symbol is recorded as `unknown`, not `neutral`.
- The pre-market report flags this in **Risk posture** and **Symbols on caution**.
- No fabricated headlines are permitted; this routine does not generate news content.

## Symbols affected
Every symbol in `config/watchlist.yaml` (24 symbols).

## Remediation suggested for follow-up routines
1. Wire SEC EDGAR fetcher (free, public) for top-holdings filings.
2. Add a curated headline RSS list for the ETFs in the universe.
3. Until then, every pre-market run will continue to flag `news_unavailable` as a risk factor.
