# Pre-Market Routine — production prompt (v1)

> Triggered by Claude Code routine schedule at 06:30 ET, Mon–Fri. Use the `orchestrator` subagent.

You are running the **PRE-MARKET** routine for today's trading date (US/Eastern).

**v1 scope reminder**: This routine produces research output only. **No trade decisions in pre-market.** The deterministic signal evaluation runs in `end_of_day` for now (since v1 doesn't run a market-open routine yet — see `config/routine_schedule.yaml`). Pre-market's job is to surface today's regime, candidates, and risk posture.

## Steps

1. Comply with `CLAUDE.md`. **Capital preservation > clever trades. When uncertain, NO_TRADE.**
2. Mode check: read `config/approved_modes.yaml`. If `mode == HALTED`, write `logs/routine_runs/<ts>_halted.md`, notify, exit.
3. Schema validation: run `python tests/run_schema_validation.py`. Halt on any failure with a `logs/risk_events/` entry.
4. Load context:
   - `config/watchlist.yaml`, `config/risk_limits.yaml`, `config/strategy_rules.yaml`
   - Last 5 `memory/daily_snapshots/<date>.md` files (one-paragraph summaries written by end_of_day — ~1 KB each, replaces reading full daily journals which can grow to 50+ KB).
   - `trades/paper/positions.json` (if exists)
   - `memory/market_regimes/current_regime.md` (if exists)
   - `memory/symbol_profiles/*.md` for each watchlist symbol (if exists)
5. **Compute everything deterministically in Python**:
   ```bash
   python3 - <<'PY'
   import json
   from lib import data, signals, config
   symbols = [s["symbol"] for s in config.watchlist()["symbols"]]
   bars = {sym: data.get_bars(sym, timeframe="1Day", limit=300) for sym in symbols}
   # VIX is not in the watchlist but is useful for regime — fetch separately if you have a feed.
   # For free Alpaca IEX, VIX isn't available; signals.detect_regime handles vix_value=None.
   regime = signals.detect_regime(bars["SPY"], vix_value=None)
   sigs = signals.evaluate_all(bars, symbols, regime, config.strategy_rules())
   print(json.dumps({
       "regime": regime.__dict__,
       "signals": [s.__dict__ for s in sigs],
   }, default=str, indent=2))
   PY
   ```
   Capture the output. **All claims in the report must reference this JSON, not invented numbers.**

6. Dispatch in parallel (each agent gets the Python output as input):
   - `market_data` — write the raw `data/market/<date>/<HHMM>.json` snapshot.
   - `news_sentiment` — last 24h headlines per symbol + sector + macro.
   - `macro_sector` — adopt the regime classification from step 5 (do not re-derive); add narrative context.
   - `technical_analysis` — wrap the `signals` output with plain-English explanation.

7. Compose `reports/pre_market/<date>.md`. Required sections:
   - **Regime**: classification (from step 5), confidence, supporting indicators (cited), counter-evidence.
   - **Today's deterministic signals**: list every Signal with action ≠ NO_SIGNAL, plus the confirmations_passed and confirmations_failed verbatim.
   - **Top candidates** (max 5): for each ENTRY signal, 1-line bull thesis, 1-line bear thesis, R/R range (from `risk_limits.default_stop_loss_pct` / `default_take_profit_pct`), invalidation, what would change the read.
   - **Symbols on caution**: ETFs with a top-holding earnings event today/tomorrow.
   - **Open positions reminder**.
   - **Risk posture**: how much of daily-trade and position budget is available.

8. Append a `## Pre-market` section to today's `journals/daily/<date>.md`.

9. Compliance/Safety reviews the report. Any rule violation → halt; do not commit broken artifacts.

10. Commit: `pre-market: research report <date> (N candidates, regime=<x>)`.

11. Notify Telegram: "Pre-market <date>: regime=<x>, N entry signals. Top: <one line>. Report: <link>."

## Constraints (v1)
- **NO trade decisions** in this routine — only candidates and theses.
- **NO writes to** `config/`, `.claude/agents/`, `prompts/routines/`, `trades/live/*`.
- **NO fabrication.** Every numeric claim cites a `lib.signals` / `lib.indicators` output.
- **Subagent dispatches must stay ≤ `risk_limits.cost_caps.max_subagent_dispatches_per_routine`.**





## Composing the Telegram notification

GitHub `/blob/main/<path>` URLs do not work reliably for our users:
- Private repos return 404 to anyone not authenticated to GitHub in the
  current browser (mobile is the common case).
- Public repos race the auto-merge action by ~30 seconds; a fast click
  hits 404 before the merge completes.

**Solution: send reports as Telegram document attachments.** No GitHub
dependency. The user reads the file inline in Telegram on any device.

### Step A — text message via `lib.notify.send_html`

Bulleted format with bold labels. `lib.notify.send_html()` uses
`parse_mode: "HTML"` so `<b>bold</b>`, `<code>code</code>`, and `•` render natively.

**Required bullets for `Pre-market` (in order):**

• <b>Regime:</b> <classification> (<low/medium/high> conf)
• <b>Signals:</b> <N> <code>ENTRY</code>, <M> <code>NO_SIGNAL</code>
• <b>Top:</b> <symbol> (<thesis one-liner>)
• <b>Mode:</b> <code>PAPER_TRADING</code> | <code>RESEARCH_ONLY</code> | …
• <b>Context:</b> ~<N> KB (cap 200 KB)              ← from audit step's approximate_input_kb
• <b>Commit:</b> <code><short SHA></code> (auto-merged to main)
• <b>Artifacts attached below:</b> <N> file(s)

Rules:
- Never mention the feature branch name.
- Notify only on action or risk event; pure no-op runs skip Telegram entirely.
- Each bullet under one line on a phone (~50–60 chars).
- Total text under 1500 chars.

### Step B — file attachments via `lib.notify.send_documents_html`

After the text message succeeds, attach the artifacts produced this run:

```bash
python3 - <<'PYNOTIFY'
from lib import notify
delivered = notify.send_documents_html([
    "reports/pre_market/<YYYY-MM-DD>.md",
    "journals/daily/<YYYY-MM-DD>.md",  # only if the daily journal has a pre-market section
])
print(f"docs delivered: {delivered}")
PYNOTIFY
```

Pass the paths most worth reading on a phone. Order matters — the first is
shown most prominently in chat. Skip files that are pure JSON dumps unless
they're tiny; markdown reports render best.

### Example for `Pre-market`

```
<b>[Calm Turtle] Pre-market 2026-05-13</b>

• <b>Regime:</b> <code>range_bound</code> (low conf)
• <b>Signals:</b> 7 <code>ENTRY</code>, 17 <code>NO_SIGNAL</code>
• <b>Top:</b> <code>GOOGL</code> (+35.3% 6m mom)
• <b>Mode:</b> <code>PAPER_TRADING</code>
• <b>Context:</b> ~18 KB (cap 200 KB)
• <b>Commit:</b> <code>d10f9b6</code> (auto-merged to main)
• <b>Artifacts attached below:</b> 2 files
```

The example shows the TEXT MESSAGE only. The attachments appear in the chat
immediately after as native Telegram document cards the user can tap to read.

## Routine audit log (mandatory final step)

Before exiting (clean OR halted OR error), write one audit file via
`lib.routine_audit`:

```bash
python3 - <<'PYAUDIT'
from lib import routine_audit
audit = routine_audit.RoutineAudit(
    routine="<routine_name_snake_case>",
    started_at="<ISO start ts>",
    ended_at="<ISO end ts>",
    duration_seconds=<float>,
    exit_reason=<"clean"|"halted"|"error"|"noop">,
    files_read=[
        routine_audit.file_record(p)
        for p in [<list of absolute paths you Read during this run>]
    ],
    subagent_dispatches={"<agent>": <count>, ...},
    artifacts_written=[<list of repo-relative paths you Wrote>],
    commits=[<short SHAs you created>],
    notes="<one-line context: anything noteworthy>",
)
routine_audit.write_audit(audit)
PYAUDIT
```

Why this exists: this is the only observable view of context-budget usage
across routine runs. `approximate_input_kb` is a proxy for input-token cost
and is trended over time. If it starts growing without bound, that's the
signal to compress per-symbol histories or rotate memory files. Until then,
we trust the system.

The hook-written `_start.md` / `_end.md` markers are separate and unchanged.

## SAFE_MODE handling (added 2026-05-14 — Plan #4)

Before any step that writes to `memory/` (except `memory/daily_snapshots/`),
to `prompts/proposed_updates/`, or that dispatches the `self_learning` agent:

```python
from lib import config, operating_mode
mode = config.current_mode()
if mode == "SAFE_MODE":
    # Skip this step entirely. The hook safe_mode_writes.sh would block
    # the file write anyway, but the routine should not attempt it —
    # it wastes tokens and pollutes the audit trail.
    pass
```

Specific steps to guard in this routine:
- Any write to `memory/symbol_profiles/`, `memory/agent_performance/`,
  `memory/prediction_reviews/`, `memory/strategy_lessons/`,
  `memory/market_regimes/` (except `current_regime.md` which is operational).
- Any dispatch of the `self_learning` subagent.
- Any write to `prompts/proposed_updates/`.

Snapshots to `memory/daily_snapshots/` are operational, not learning, and
remain allowed in SAFE_MODE.

When `mode == SAFE_MODE`, the Telegram notification should append:
```
• <b>Mode:</b> <code>SAFE_MODE</code> (learning suppressed)
```

The routine_audit appendix MUST record `mode: SAFE_MODE` and a count of
skipped learning steps so the audit trail clearly shows learning was
intentionally suppressed.
