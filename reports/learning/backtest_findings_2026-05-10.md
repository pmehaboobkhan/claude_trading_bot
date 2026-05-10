# Backtest Findings — 2026-05-10

> First end-to-end backtest of the Calm Turtle strategy library. This report documents what we learned and what changes to make before any paper trading.

## TL;DR

Across **7 backtests** (2 production strategies + 5 sweep variants) over 2022-01-25 → 2026-05-08, **zero variants beat SPY** on a long-only sector-ETF universe. The best variant captures roughly half of SPY's return with two-thirds of SPY's drawdown. **No strategy meets the promotion criteria. Nothing graduates to paper trading.**

This is a successful outcome. The deterministic backtest harness did exactly what it was supposed to do — surfaced a structural mismatch before money was at risk.

---

## What we tested

| | Strategy | Description |
|---|---|---|
| 1 | `sector_relative_strength_rotation` (baseline) | top-3 RS entry / top-5 exit, 20d/60d windows |
| 2 | `regime_defensive_tilt` | XLP/XLU/XLV entry on risk-off, XLK/XLY/XLC exit on risk-off |
| 3-7 | Param sweep on rotation | 5 variants of (windows, top-N entry, top-N exit) |

Universe: SPY + 11 GICS sector SPDRs. Window: 2022-01-25 → 2026-05-08 (~4.3 years, 1076 trading days after 200-day warmup). Capital: $100k. Fill model: 1bp slippage + 1bp half-spread per side (~4bps round-trip friction). Alpaca free IEX feed.

Two **deterministic** bugs the backtest exposed and we fixed during this session:

1. **No EXIT logic in either strategy** — both originally emitted only ENTRY/NO_SIGNAL, so once entered, positions sat for years. Fixed by adding EXIT with hysteresis (top-3 entry / top-5 exit buffer for rotation; risk-on-returns EXIT for defensive tilt).
2. **Promotion criteria were too lenient** — "beats equal-weight sectors" is a low bar; cap-weighted SPY usually outperforms equal-weight in tech-led regimes. Tightened to require beating both SPY AND equal-weight.

## Results — production strategies

| Strategy | Return | Max DD | Sharpe | Trades | α vs SPY | α vs EW | Promotion? |
|---|---:|---:|---:|---:|---:|---:|---|
| RS Rotation | **+11.79%** | **15.18%** | 0.35 | 114 | −57.99% | +4.07% | **NO** (fails SPY bar) |
| Defensive Tilt | +3.78% | **11.83%** | 0.16 | 77 | −65.99% | −3.93% | **NO** (fails EW AND SPY) |
| SPY buy & hold | +69.77% | 22.74% | n/a | 0 | 0 | +62.05% | — |
| Sector EW buy & hold | +7.72% | n/a | n/a | 0 | −62.05% | 0 | — |

The drawdown story is genuine: RS rotation cuts drawdown by ~7.5 percentage points vs SPY. If the goal had been *"stay invested but suffer less in bear markets"*, this is a real and measurable edge. But the stated goal in `CLAUDE.md` is **beat SPY risk-adjusted with drawdown ≤ SPY's** — and on absolute return alone, we're nowhere close.

## Results — parameter sweep

Tested on the same in-sample window. Honest about overfitting risk: with only 4.3 years of data, picking the "best" variant from this sweep doesn't prove it'll work going forward.

| Variant | Return | α vs SPY | α vs EW | Trades | Notes |
|---|---:|---:|---:|---:|---|
| concentrated_20_60_2_3 | **+16.61%** | −53.17% | **+8.89%** | 89 | Best — more concentration helps |
| baseline_20_60_3_5 | +11.79% | −57.99% | +4.07% | 114 | Production default |
| faster_concentrated_10_30_2_3 | +9.55% | −60.22% | +1.83% | 128 | Speed adds noise, hurts |
| faster_10_30_3_5 | +9.39% | −60.38% | +1.68% | 183 | Worst-for-the-trade-count |
| slow_60_120_3_5 | −0.28% | −70.06% | −8.00% | 98 | Slow windows lag too much |

**Observations:**
- Concentration helps. Top-2 outperforms top-3 in this window. The intuition: in a tech-led regime, narrower concentration on whichever 1-2 sectors are leading captures more of the dominant trend.
- Speed hurts. Faster windows (10/30d) generate more trades and more noise, with lower net return.
- Even the best variant is **−53% alpha vs SPY**. Tuning parameters doesn't fix the structural mismatch.

## What it means (the honest read)

### 1. The structural problem

SPY is cap-weighted, so it heavily holds the same mega-caps (NVDA, MSFT, AAPL) that consistently top the sector-RS rankings via XLK/XLC. When XLK falls out of top-3 RS, we sell it. But SPY *keeps holding* the same names because they're still ~30% of the index. We're effectively underweight-vs-SPY exactly when we should be neutral.

This is the fundamental challenge: **long-only sector rotation cannot beat a cap-weighted index whose top weights consistently top the rankings.** Adding leverage, shorts, or single-stock concentration could fix it. We explicitly excluded those for v1.

### 2. What the sweep *does* tell us

- Concentration > diversification (in this regime).
- Slow > fast windows (less whipsaw).
- The framework, hooks, and reporting machinery all work as designed.

### 3. What the sweep does NOT tell us

- Whether any variant works **out-of-sample** — we tested all 5 on the same window.
- Whether any variant works in a **different regime** (e.g., 2000-2010 "lost decade," 2008 GFC). Alpaca's free tier has limited pre-2018 data, so we don't yet have an honest answer.

## Recommendations going forward

Four options, ordered by how much I'd defend each:

### A. **Stop here, buy SPY.** (Highest intellectual honesty)
The most rigorous response to a failed backtest is to update your beliefs. Long-only sector rotation under our constraints, in our universe, with our chosen benchmarks, does not produce edge over SPY. The 4 weeks we invested in this project paid for itself in *not* spending months paper-trading something that wouldn't have worked.

### B. **Accept a different goal: lower-DD-with-lower-return.** (Defensible if you want one)
If your actual goal is *"capital preservation > clever trades"* (as `CLAUDE.md` says) and you'd genuinely take 12% over 4 years with a 15% max drawdown instead of 70% with a 23% drawdown, then RS rotation *does* deliver something useful. Reframe the goal in `CLAUDE.md` from "beat SPY" to "lower-drawdown SPY-correlated equity exposure." Paper-trade the concentrated 20/60 variant for 60+ days. Don't lie to yourself about edge — this is a *defensive overlay*, not alpha.

### C. **Lift the long-only constraint.** (Best chance of real edge, biggest scope expansion)
Add short positions on underperforming sectors and/or leverage on outperformers. Pair-trade XLK long / XLP short when in bull regime, flip in bear. This is a structurally different system and would require new strategies, new risk rules (margin permissions, drawdown caps for short exposure), new fill modeling. **Multi-week scope expansion.** Could produce real alpha, but also real losses.

### D. **Test on different time windows.** (Quick, easy, may not change conclusion)
Pull XLK/XLF/etc. data from Yahoo / Stooq / other free sources for 2005-2015 (financial crisis + recovery + lost-decade-end). Re-run the sweep. If RS rotation also lost to SPY there, the structural conclusion holds. If it beat SPY there, we know the issue is regime-specific — and we have a more nuanced position. **A few hours of work.**

## My recommended next step

**Do D first** (other-time-window test). Cheapest information per hour. If D confirms the structural conclusion, do B (reframe goal, paper-trade conservatively) OR A (stop). If D refutes the conclusion (RS works in some regimes), we have a richer choice between B/C and can revisit.

What I'd **not** do without thinking hard first:
- Iterate on parameters within the same window (further overfitting risk).
- Add more strategies (more complexity, same structural problem).
- Skip ahead to paper-trading RS rotation and hope.

---

# Update — Option D Results (out-of-regime validation, 2026-05-10)

Ran the full 5-variant parameter sweep against three historical regimes using yfinance daily bars (Yahoo's free feed; production code remains Alpaca-only). Script: `scripts/yfinance_sweep.py`.

## Cross-regime summary

| Window | Period | SPY return | Sector EW | Best strategy α vs SPY | Any variant beat SPY? |
|---|---|---:|---:|---:|---|
| Post-GFC recovery | 2010-10-19 → 2015-12-31 | +94.51% | +88.73% | **−77.68%** | **NO** |
| Pre-Mag-7 + COVID (truncated) | 2019-04-05 → 2020-12-31 | +33.89% | +23.68% | **−31.24%** | **NO** |
| Mag-7 era | 2022-10-19 → 2026-05-08 | +109.76% | +78.11% | **−74.00%** | **NO** |

*Caveat: the 2015-2020 window was truncated to ~1.5 years because XLC inception was June 2018; aligning the full 11-sector universe left only 640 common days. A 10-sector version (dropping XLC) would give a longer window. Even so, the result direction is unambiguous.*

## What this means

**The structural hypothesis is rejected. The strategy doesn't work across regimes — not just in the Mag-7 era.**

In 2010-2015 — a value-led, financials-led, NOT tech-led regime — the rotation strategy still lost to SPY by 78 percentage points. That period was the *exact* counterfactual we needed. If the strategy were going to work anywhere, it should have worked there. It didn't.

Two structural reasons (revised after Option D):

1. **RS rotation lags.** By the time a sector clears top-3 RS on both 20d AND 60d windows, the move is well-established. We're buying after the leg up.
2. **SPY's silent re-weighting wins.** SPY's cap-weighting *passively* drifts toward whatever's winning (via market cap rising). Our explicit rotation tries to do the same thing but with delay, friction, and tax events. Passive cap-weight beats explicit rotation on the same logic, at zero cost.

## Updated conclusion

The earlier finding ("can't beat SPY in Mag-7 era") was too narrow. The correct finding is:

> **Long-only sector ETF rotation with relative-strength rules, as currently specified, does not produce edge over SPY in any of three tested regimes (2010-2015, 2019-2020, 2022-2026).** The structure of cap-weighted index investing is *itself* the rotation strategy you're trying to build, but executed continuously and at zero cost.

This is a stronger finding than what we had before — and it's the kind of finding that should change behavior.

## Updated recommendations (revised after Option D)

The earlier four options now collapse to a much smaller decision space:

### A. Stop. Buy SPY. (Strongly recommended)
Three regimes of evidence say long-only sector ETF rotation doesn't beat the index. Adding more variants, more parameters, or longer paper-trading windows is unlikely to change that. The honest move is to stop and update your beliefs about what kind of system *could* produce edge.

### B. Reframe goal to "drawdown management." (Defensible)
The drawdown story is robust across windows: rotation cuts max DD by 5-7 percentage points vs SPY. If your actual goal becomes *"stay long equities but bleed less in drawdowns,"* the existing strategy delivers something real. But understand what you're getting: lower returns, lower drawdowns, **negative alpha**. This is a portfolio-level risk-management tool, not an investment edge. If you'd prefer that to SPY, paper-trade it. Be honest in `CLAUDE.md` about the new goal.

### C. Change kind, not parameters. (Bigger scope)
If you actually want a chance at beating SPY, the system needs structurally different mechanics:
- **Long-short pair trades** between sectors.
- **Concentrated single-stock momentum** (which we said we wouldn't do because LLMs aren't reliable here — but a deterministic momentum rule could be).
- **Trend-following on individual mega-caps** with leverage capped at 1x.
- **Tactical allocation between SPY and treasuries** based on regime (drawdown timing).

These are all bigger projects with different risk profiles. None are obviously profitable; all require the same backtest-first discipline we just used.

### D. Look further back. (Confirmation only)
We could pull 2000-2010 or pre-2000 data to add a fourth regime. Almost certainly confirms the conclusion. Not worth the time given current evidence.

## My honest call

**Recommend A or B**, leaning toward A if you can stomach the un-glamorous answer.

A is the intellectually honest move. We built infrastructure, tested rigorously, found no edge across three regimes, and the right response is to update beliefs.

B is defensible if you'd genuinely prefer lower-DD equity exposure to SPY — but only if you reframe the goal honestly and don't pretend you have alpha when you don't.

C is interesting but a different project; don't drift into it as a face-saving move. Decide separately if you want to start a "v2 ambitious" project.

## What this session was actually worth

Don't lose sight of: **this is exactly what we wanted the backtest harness to do.** A week of paper trading wouldn't have produced this clarity. A month of paper trading would have produced a misleading "RS rotation makes 12% with low DD!" narrative that you'd have to spend more months *un*learning. We have the answer in an afternoon.

The deterministic infrastructure paid for itself before placing a single trade.

## Status updates to apply

| File | Change |
|---|---|
| `config/strategy_rules.yaml` | Mark `sector_relative_strength_rotation` → `UNDER_REVIEW` (not promotion-eligible). Mark `regime_defensive_tilt` → `REJECTED`. |
| `config/approved_modes.yaml` | Stay on `RESEARCH_ONLY`. Do NOT promote to `PAPER_TRADING`. |
| `CLAUDE.md` | If choosing option B, update primary goal from "beat SPY risk-adjusted" to "lower-drawdown equity exposure vs SPY." Do not silently keep the old goal. |
| This document | Frozen — `reports/learning/` is append-only memory. Next decisions go in a new dated file. |

## Status summary for `strategy_rules.yaml`

| Strategy | Backtest? | Promotion? | Status proposal |
|---|---|---|---|
| sector_relative_strength_rotation | ✅ | ❌ (fails SPY bar) | Keep `ACTIVE_PAPER_TEST` flag for backtest purposes, but `RESEARCH_ONLY` mode in v1 ensures no paper trades. Don't flip mode to PAPER_TRADING. |
| regime_defensive_tilt | ✅ | ❌ (fails EW and SPY) | Should be marked `UNDER_REVIEW` or `REJECTED`. Don't paper-trade. |
| trend_pullback_in_leader | ❌ not backtested yet | n/a | Keep `NEEDS_MORE_DATA`. |
| spy_neutral_default | n/a (it's the default) | n/a | Keep `ACTIVE_PAPER_TEST`. It's just "hold SPY." |

## Evidence trail

- Production backtests: `backtests/sector_relative_strength_rotation/2022-01-25_to_2026-05-08.md`, `backtests/regime_defensive_tilt/2022-01-25_to_2026-05-08.md`
- Sweep results: `backtests/param_sweep/<variant>/2022-01-25_to_2026-05-08.md` (5 variants)
- Scripts: `scripts/run_backtest.py`, `scripts/run_param_sweep.py`
- Strategy code: `lib/signals.py` (post EXIT-logic refactor, 2026-05-10)
- Backtest engine: `lib/backtest.py` (tightened promotion criteria, 2026-05-10)
