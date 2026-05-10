# Calm Turtle — Operating Manual

> This file is the repo-level operating manual. Every Claude Code routine and agent reads it on every run. Comply with every rule below. When uncertain, **choose NO_TRADE**.

## Project purpose

This repository runs a Claude-native research and paper-trading workflow for a 12-symbol U.S. sector-ETF universe. The goal is **risk-adjusted outperformance vs SPY** (Sharpe with max drawdown ≤ SPY's), measured against:

1. **SPY** (the stated risk-adjusted target).
2. **Equal-weight buy-and-hold of the 11 sector ETFs** (the "is the trading itself adding value?" test).

It is **not** a guaranteed-income system. Markets are risky; losses are possible.

## Operating modes

The current mode lives in `config/approved_modes.yaml`. Read it on every routine start. If unreadable or the file is missing, halt the routine.

- `RESEARCH_ONLY` — produces reports and decisions; no paper or live trades.
- `PAPER_TRADING` — simulates fills via internal simulator or Alpaca paper API.
- `LIVE_PROPOSALS` — emits `PROPOSE_LIVE_*` decisions for human approval. No live orders.
- `LIVE_EXECUTION` — Phase 8+ only; places live orders within hard limits.
- `HALTED` — refuses all trading-hour routines; allows read-only inspection.

## Safety rules (non-negotiable)

1. **Never edit any of these files**. Changes require a human-reviewed PR:
   - `config/risk_limits.yaml`
   - `config/strategy_rules.yaml`
   - `config/approved_modes.yaml`
   - `config/watchlist.yaml`
   - `.claude/agents/*.md`
   - `prompts/routines/*.md`
2. **Never trade a symbol** that isn't in `config/watchlist.yaml` with the appropriate `approved_for_*` flag set to `true`.
3. **Never raise risk limits.** You may only **propose** changes via `prompts/proposed_updates/` or PR drafts.
4. **If `approved_modes.yaml` mode is `HALTED`**, all routines exit early after writing a record to `logs/routine_runs/`.
5. **If data is stale** beyond `risk_limits.yaml > data > max_data_staleness_seconds`, produce `NO_TRADE` decisions and stamp the staleness in the journal.
6. **Refuse live execution.** v1 produces only paper trades or live proposals. Any code path that would place a live order without `mode == LIVE_EXECUTION` is blocked by hook #1 and must not be circumvented.

## Approved write paths

You **may** write to:

- `journals/daily/<today>.md` (only today's; older are immutable)
- `journals/weekly/`, `journals/monthly/` (current period only)
- `decisions/<today>/<HHMM>_<SYM>.json`
- `decisions/by_symbol/<SYM>.md` (append-only)
- `trades/paper/log.csv` (append-only) and `trades/paper/positions.json`
- `reports/pre_market/`, `reports/end_of_day/`, `reports/learning/`
- `data/market/`, `data/news/`, `data/fundamentals/`
- `logs/routine_runs/`, `logs/risk_events/`
- `memory/` (observation files; per per-folder rules)
- `prompts/proposed_updates/` (drafts only)

You **may not** write to:

- `config/*` (PR only)
- `.claude/agents/*.md` (PR only)
- `prompts/routines/*.md` (PR only)
- `trades/live/*` (until Phase 8 + explicit mode change)
- Any historical journal (older than 24 h)
- Existing rows of any append-only file

## Prohibited actions

- Trading any symbol not in `config/watchlist.yaml`.
- Running any strategy not in `config/strategy_rules.yaml > allowed_strategies`.
- Raising any risk limit.
- Activating live mode without explicit human PR.
- Margin, options, short selling, leveraged ETFs, or averaging down unless explicitly enabled in `risk_limits.yaml`.
- Skipping the Risk Manager or Compliance/Safety gates.
- Producing any trade decision without bull thesis, bear thesis, and invalidation condition.
- Fabricating data or news. Every data point cites a source.

## Trading limitations (v1)

- Paper trading only. Long-only ETFs.
- Universe = 12 sector ETFs (see `config/watchlist.yaml`).
- Risk Manager enforces per-position, total-exposure, sector-correlation, daily-loss, weekly-loss, monthly-loss, and consecutive-loss limits.
- A trade only opens when **all** of: R/R ≥ minimum threshold; data fresh; Risk Manager APPROVES; Compliance/Safety APPROVES.

## Journaling requirements

- Every routine appends to today's daily journal.
- Every decision is recorded — including `NO_TRADE`.
- A "what failed" section is mandatory even on profitable days.
- Reflective lessons go to `memory/` (and to `prompts/proposed_updates/` for prompt changes), never directly into production prompts.

## Git commit requirements

- Every routine run produces exactly one commit (or zero if nothing changed).
- Commit messages follow `docs/commit_messages.md`.
- Never force-push. Never amend public commits.
- Co-author trailer:
  ```
  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  ```

## Human approval requirements

The following changes always require a PR reviewed by a human (never a direct commit):

- `config/risk_limits.yaml`
- `config/strategy_rules.yaml`
- `config/approved_modes.yaml`
- `config/watchlist.yaml` (any change to live flags; new-symbol additions; max position sizes)
- broker permissions (live keys, scopes)
- `.claude/agents/*.md`, `prompts/routines/*.md`

Promoting a strategy from `ACTIVE_PAPER_TEST` to live → human only.
Adding a new symbol to the watchlist → human only (Self-Learning Agent may **propose** in `prompts/proposed_updates/watchlist_additions.md`).

## Handling missing data

- News connector down → mark symbols `news_unavailable`; treat as **risk factor**, not as "no news = bullish."
- Market data stale → `NO_TRADE` for affected symbols; log to `logs/risk_events/`.
- Fundamentals stale > 90 days → flag in decision; do not trade earnings-window setups.
- Any missing input is a reason to be **more conservative**, never less.

## Conflicting agent outputs

- TA bullish vs News bearish vs Macro neutral → Trade Proposal must surface the conflict in `thesis_bear` and lower `confidence_score`.
- Risk Manager always wins ties.
- Compliance/Safety always wins, period.

## How to halt safely

- Set `config/approved_modes.yaml > mode: HALTED` via the `/halt-trading <reason>` slash command, which writes a paired `logs/risk_events/` entry. Direct edits without the audit-log pair are rejected by hook #11.
- Resume requires a human PR explicitly setting mode back.

## Performance tracking (every weekly and monthly review)

- Period return (paper portfolio) vs **SPY** total return.
- Period return vs **equal-weight buy-and-hold of the 11 sector ETFs**.
- Alpha vs each benchmark.
- Sharpe ratio (or simplified return / volatility for short windows).
- Max drawdown vs SPY's max drawdown.
- Beta to SPY.
- Information ratio.
- Confidence calibration: predicted-confidence buckets vs realized hit rate.

If the system fails either benchmark on a 3-month rolling basis, the monthly review must recommend `STAY_PAPER` or `HALT_AND_REVIEW`. Live trading does not unlock until both benchmarks are beaten on a 6-month risk-adjusted basis.
