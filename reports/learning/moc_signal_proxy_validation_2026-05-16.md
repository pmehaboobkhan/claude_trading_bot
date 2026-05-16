# MOC signal-proxy validation — 2026-05-16

**Option B gate (Approach A: empirical decision-agreement).** Fills are unaffected (MOC = official close = backtest assumption); this measures only whether a ~15:50 signal input changes the decision vs the true 16:00 close.

- Sample: last `60d` of `5m` bars; proxy = last intraday close at/before **15:50 ET** (a conservative upper bound — the real 15:50 proxy is closer to the close than this).
- Days evaluated: **60**
- Decision-agreement rate: **0.8667** (threshold 0.99)
- Regime-flip days: **4**
- Per-strategy divergences: `{'large_cap_momentum_top5': 14}`

## Provisional verdict: **FAIL**

> Recommendation input only. Human PR approval is still required, and every divergent day below must be inspected for whether the true-close decision was itself borderline (a borderline flip is not a methodology failure — it resolves the same way live).

### Reasons
- agreement_rate 0.8667 < required 0.99
- 4 day(s) had a regime-label flip — inspect each

### Divergent days (manual borderline review required)

- **2026-02-27** regime range_bound→uncertain; [{'strategy': 'large_cap_momentum_top5', 'symbol': 'AAPL', 'close_action': 'NONE', 'proxy_action': 'EXIT'}, {'strategy': 'large_cap_momentum_top5', 'symbol': 'PFE', 'close_action': 'EXIT', 'proxy_action': 'NONE'}]
- **2026-03-02** regime range_bound→bullish_trend; [{'strategy': 'large_cap_momentum_top5', 'symbol': 'PFE', 'close_action': 'NONE', 'proxy_action': 'ENTRY'}, {'strategy': 'large_cap_momentum_top5', 'symbol': 'TSLA', 'close_action': 'ENTRY', 'proxy_action': 'NONE'}]
- **2026-03-06** regime range_bound→uncertain; [{'strategy': 'large_cap_momentum_top5', 'symbol': 'CSCO', 'close_action': 'NONE', 'proxy_action': 'ENTRY'}, {'strategy': 'large_cap_momentum_top5', 'symbol': 'TSLA', 'close_action': 'ENTRY', 'proxy_action': 'NONE'}]
- **2026-03-11** regime uncertain→uncertain; [{'strategy': 'large_cap_momentum_top5', 'symbol': 'CSCO', 'close_action': 'NONE', 'proxy_action': 'ENTRY'}, {'strategy': 'large_cap_momentum_top5', 'symbol': 'TSLA', 'close_action': 'ENTRY', 'proxy_action': 'NONE'}]
- **2026-04-17** regime range_bound→range_bound; [{'strategy': 'large_cap_momentum_top5', 'symbol': 'PFE', 'close_action': 'NONE', 'proxy_action': 'ENTRY'}, {'strategy': 'large_cap_momentum_top5', 'symbol': 'WMT', 'close_action': 'ENTRY', 'proxy_action': 'NONE'}]
- **2026-04-20** regime bullish_trend→range_bound; []
- **2026-04-22** regime range_bound→range_bound; [{'strategy': 'large_cap_momentum_top5', 'symbol': 'AMZN', 'close_action': 'NONE', 'proxy_action': 'ENTRY'}, {'strategy': 'large_cap_momentum_top5', 'symbol': 'JNJ', 'close_action': 'ENTRY', 'proxy_action': 'NONE'}]
- **2026-05-05** regime bullish_trend→bullish_trend; [{'strategy': 'large_cap_momentum_top5', 'symbol': 'COST', 'close_action': 'NONE', 'proxy_action': 'EXIT'}, {'strategy': 'large_cap_momentum_top5', 'symbol': 'PFE', 'close_action': 'EXIT', 'proxy_action': 'NONE'}]

### Analytical sanity bound (Approach B)
The strategies are low-frequency: `dual_momentum_taa` uses a ~210-day SMA trend filter, `large_cap_momentum_top5` ranks by ~126-day return, `gold_permanent_overlay` is price-insensitive. A ~10-minute last-bar move shifts a 210-day SMA by ≈Δ/210 and a 126-day return by a comparably tiny amount, so a decision can only flip when it was already on a knife-edge at the true close — i.e. resolves the same way live. The empirical rate above quantifies how often that knife-edge actually occurs.
