# Historical Universe Methodology

## Purpose

Replace Strategy B's modern-basket survivor-biased universe with a year-by-year approximation of
the actual S&P 100 (or top-30 by market cap) membership. Used by
`scripts/run_survivor_bias_stress.py` to produce an honest measurement of the survivor-bias
haircut.

## Data structure

`data/historical/sp100_as_of.json`:

```json
{
  "2005": ["AAPL", "MSFT", "INTC", "CSCO", "GE", "XOM", "WMT", "C", "BAC", "JNJ", ...],
  "2006": [...],
  ...
  "2026": [...]
}
```

The list for year YYYY is the universe active for the entire calendar year YYYY. Strategy B's
top-N selection at date D uses the list for `year(D)`.

## Sources

- Wikipedia "S&P 100 Index" article history (revision dates near each year-end).
- StockAnalysis.com / Slickcharts archived S&P 100 lists.
- SEC 10-K filings for individual names (to confirm a name was operating + listed in a given year).
- Cross-check against yfinance: every symbol in the table MUST have bars covering at least the
  year(s) it appears in.

## Known approximations

- Index changes mid-year are NOT modeled. A symbol added in July 2010 is treated as either
  present or absent for all of 2010 — typically we treat it as **absent** that year (conservative).
- Symbols that were renamed (e.g., FB → META, GOOG → GOOGL share class) are treated using the
  symbol that was active that year.
- Mergers (e.g., XOM + Mobil = XOM; PFE + Wyeth = PFE; T + BLS = T) use the surviving ticker.
- Bankruptcies (Lehman 2008-09, GM 2009-06, Citi rescue) are **important to include** for the
  year(s) they were in the index, even if they were later removed. The whole point of this
  exercise is that a 2008-vintage portfolio might have held them.

## Year-by-year curation notes

### 2005–2007
Core S&P 100 with large financial, energy, and industrial names. Tech sector led by Intel, Cisco,
IBM, Oracle, Dell, HP — before Apple's explosive growth. GM and Ford present in the index.
Citi, Merrill, Bear Stearns, Wachovia all large financials. No Google until 2006 (IPO was late
2004 but it takes time to enter the S&P 100).

### 2008 (crisis year — critical to get right)
Includes pre-collapse financials: Lehman Brothers (LEH, bankrupt September 2008), Bear Stearns
(BSC, collapsed March 2008 and acquired by JPM), Wachovia (WB, acquired by Wells Fargo), Merrill
Lynch (MER, acquired by BofA), AIG (bailed out September 2008). These MUST appear in 2008 because
any portfolio running at the start of 2008 would have had exposure to them.

### 2009–2011
Drops 2008 bankruptcies/acquisitions. GM goes bankrupt June 2009, relisted October 2010 under new
ticker GM — treated as absent 2009, reinstated 2010 conservatively. Citigroup reverse-split and
effectively dropped from the top-100 by market cap for several years (included 2009, dropped 2010).
TSLA added 2010 (IPO June 2010 — included starting 2011 conservatively). The 2010+ universe shifts
toward tech as AAPL, AMZN, GOOG grow.

### 2012–2013
Facebook (FB) IPO May 2012 — added from 2013. Netflix (NFLX) grows in prominence.

### 2014–2015
Google reclassifies shares to GOOGL / GOOG in April 2014. We use GOOGL (voting shares) from 2014.
Energy sector strong due to high oil prices.

### 2016–2018
Energy names decline with lower oil. AMZN market cap grows explosively. NFLX, NVDA grow in
prominence.

### 2019–2020
COVID year 2020 — ZM, MRNA enter prominence but not modeled here. We focus on pre-existing S&P 100
names. WMT and COST gain amid pandemic; energy names drop precipitously.

### 2021–2023
Growth-to-value rotation. Meta (FB → META, renamed October 2021 — use META from 2022). NVDA
dominates. Tesla added to S&P 500 December 2020; large enough for S&P 100 by 2021. Berkshire
(BRK.B) grows.

### 2024–2026
AI-driven tech dominance. Magnificent 7 (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA) in
universe. Traditional industrials and financials still present but with lower weight.

## Validation rule

For each year Y: every symbol in the list must have at least one yfinance bar dated YYYY-01-15 ± 30
days. Run `lib.historical_membership.validate_universe()` after every edit.

Note: Delisted names (LEH, BSC, WB) have yfinance bars through their delisting date but not after.
The stress-test framework treats missing bars as "symbol not tradeable on that date" — Strategy B
skips symbols without enough momentum-window history, so LEH and BSC being in the 2008 universe
without 2009 bars correctly models the bankruptcy loss.

## Maintenance

Append new year entries each January. Do not modify historical entries (append-only contract).
