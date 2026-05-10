---
description: Deep-dive a single watchlist symbol. Refuses if symbol is not in config/watchlist.yaml.
argument-hint: "<SYMBOL>"
---

Analyze symbol `$1`.

1. Read `config/watchlist.yaml` and verify `$1` is present and `approved_for_research: true`. If not, refuse with a clear message and exit. Do not analyze symbols outside the watchlist.
2. Use the `market_data`, `technical_analysis`, `fundamental_context`, and `news_sentiment` subagents in parallel.
3. Synthesize findings into `reports/symbol_deep_dive/$1_<YYYY-MM-DD>.md`.
4. Do NOT produce a trade decision from this command — this is research-only output.
5. Notify when done.
