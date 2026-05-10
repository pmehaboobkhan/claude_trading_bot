# Model Limitations

> What this system CANNOT do, written down explicitly so we don't kid ourselves.

## What an LLM-driven trading system can plausibly do

- Read and synthesize news, filings, and macro context faster than a human can each morning.
- Detect regime shifts (with lag) by combining multiple indicators.
- Apply discipline — execute the rules in `risk_limits.yaml` and `strategy_rules.yaml` without emotion.
- Track per-symbol behavior and per-agent calibration over time.
- Produce auditable, reviewable explanations for every decision.

## What it CANNOT do

- **Forecast earnings** better than sell-side analysts.
- **Predict price moves** intraday — microstructure beats LLM reasoning at every timescale shorter than ~hours.
- **Beat factor models** at picking single-stock alpha.
- **Time market tops or bottoms.** Regimes shift in ways LLMs notice with lag.
- **Find arbitrage.** That's HFT territory.
- **Replace a financial advisor or accountant.** Tax, estate, and personal-finance advice is human.

## Failure modes specific to LLM agents

- **Hallucinated facts**: an agent may fabricate a headline or a number. Mitigation: every claim must cite a source URL or named indicator. News & Sentiment requires ≥ 2 sources for material classifications.
- **Confirmation bias on accepted strategies**: once a strategy is "ours," agents over-reason in its favor. Mitigation: Self-Learning Agent must include counter-hypothesis on every proposal.
- **Recency bias**: a strong week is easily mistaken for a real edge. Mitigation: sample-size guardrails (N ≥ 20 for strategy claims, N ≥ 5 for symbol claims; below that → `PRELIMINARY`).
- **Correlated errors across agents**: if all agents share the same wrong premise (e.g., wrong regime call), the entire decision goes wrong together. Mitigation: regime calls require ≥ 3 supporting indicators + counter-evidence; Compliance/Safety reviews independently.
- **Over-eager proposals**: too many prompt updates, too fast, drowning the human reviewer. Mitigation: ≤ 5 prompt proposals + ≤ 3 strategy proposals + ≤ 1 risk-rule review per Self-Learning cycle.
- **Calibration drift**: an agent's confidence steadily becomes worse-correlated with hit rate. Mitigation: weekly calibration histograms; drift in Risk Manager / Compliance triggers `HALT_AND_REVIEW`.

## Edge thesis (and where it could break)

The system bets that **macro/sector context synthesis + discipline** is enough to outperform passive equal-weight 11-sector buy-and-hold on a risk-adjusted basis.

Ways this thesis could be wrong:
- Sector rotation alpha doesn't actually exist after costs and slippage.
- LLMs can't synthesize macro better than just following price-based RS rankings.
- The discipline from following rules is offset by occasional rule-breaking from LLM ambiguity.
- Survivorship in past data ≠ predictive power going forward.

Ways we'll know:
- Monthly review reports paper portfolio vs equal-weight 11-sector.
- If we underperform equal-weight on a 3-month rolling basis, the recommendation downgrades to `STAY_PAPER` and we ask: is the trading adding value or just adding tax events?

## What "we don't know" looks like in practice

When the system writes "we don't know," it should look like:
- `regime: uncertain` (rather than picking a regime to feel decisive).
- `NO_TRADE` with reason `confirmations_incomplete` (rather than trading on 2 of 3 confirmations).
- `confidence_score: 0.4` (rather than rounding to 0.6 to feel confident).
- `news_unavailable` flagged as a risk factor (rather than treating silence as bullish).

The system that says "I don't know" more often is the system that survives.
