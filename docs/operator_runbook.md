# Operator Runbook

> The day-to-day "what do I do" guide. Read once, refer back as needed.

## Daily

| Time (ET) | What runs | What you do |
|---|---|---|
| 06:30 | Pre-market routine | Read the Telegram summary. Optionally open the report. |
| 09:35 | Market open | Read the summary. If anything unusual, open the daily journal. |
| 12:00 | Midday | Notification only on action / risk events. |
| 15:30 | Pre-close | Same. |
| 16:30 | End-of-day | Read PnL + top lesson. |

## Weekly

- **Saturday 09:00 ET** — weekly review fires. Open the report at `reports/learning/weekly_learning_review_<date>.md`. Skim "items requiring human approval" and "recommended prompt updates."
- Decide on each pending proposal. Merge or close PR drafts in `prompts/proposed_updates/`.

## Monthly

- **1st of month 09:00 ET** — monthly review fires. The mode recommendation at the top is the most important field. Default expectation: `STAY_PAPER` for a long time.

## When something goes wrong

| Symptom | What it means | Action |
|---|---|---|
| Telegram URGENT alert | Risk event or compliance breach | Open `logs/risk_events/`. Investigate. Consider `/halt-trading <reason>`. |
| Routine missed | Schedule didn't fire, or routine errored | Check `logs/routine_runs/`. If errored, fix and `/<routine>` manually. |
| Reconciliation failure at EOD | `trades/paper/log.csv` ↔ `positions.json` mismatch | Halt trading. Manually reconcile via `python -c "from lib.paper_sim import reconcile; print(reconcile())"`. |
| Unexpected drawdown | Daily / weekly / monthly loss approached limit | Risk Manager should already be enforcing. Verify with `/risk-check`. |
| Schema validator complaints | A config file is malformed | Fix and re-run `python tests/run_schema_validation.py`. |

## Halting

- `/halt-trading <reason>` — flips mode to `HALTED`, writes paired audit log, notifies.
- Resume: open a PR editing `config/approved_modes.yaml` to restore the prior mode. The system will not resume itself.

## Adding a watchlist symbol (manual only)

1. Open a PR editing `config/watchlist.yaml`.
2. Default the new symbol to `approved_for_research: true`, **`approved_for_paper_trading: false`** for at least 2 weeks while a `memory/symbol_profiles/<SYM>.md` accumulates baseline data.
3. After 2 weeks, separate PR to flip `approved_for_paper_trading: true`.
4. `approved_for_live_trading` always stays `false` until Phase 8.

## Promoting a strategy

1. The Self-Learning Agent will draft a `STRATEGY_REVIEW_REQUIRED` doc in `prompts/proposed_updates/`.
2. Open a PR editing `config/strategy_rules.yaml` if you accept.
3. Hook `require_strategy_tests.sh` will (eventually) require a `tests/strategies/<name>_test.md` for any promotion to `ACTIVE_PAPER_TEST`.

## Key rotation (quarterly)

1. Rotate keys at `app.alpaca.markets`.
2. Update Claude Code routine secrets (and `.env.local` if you use it).
3. Rotate Telegram bot token via @BotFather only if compromised — otherwise leave alone.
4. Document rotation in `docs/risk_profile.md > rotation_history`.

## Alpaca paper-account mirror mode (BROKER_PAPER)

By default the system uses an internal CSV simulator for fills (`BROKER_PAPER=sim`,
or unset). Trades land in `trades/paper/log.csv` + `positions.json` only — **nothing
reaches Alpaca**. To enable real Alpaca paper trades:

### One-time enablement (operator-run, ~5 min)

1. Confirm credentials are set in the cloud routine env:
   - `ALPACA_PAPER_KEY_ID`
   - `ALPACA_PAPER_SECRET_KEY`
2. Sanity check from a local shell (with creds in env): `python3 scripts/sync_alpaca_state.py`
   - Reports current local-vs-Alpaca divergence. Expect divergence on first run.
3. **Fresh-start the state** (DESTRUCTIVE — closes all Alpaca positions, clears local):
   ```bash
   python3 scripts/sync_alpaca_state.py --reset-fresh-start
   ```
   Writes a paired `logs/risk_events/<ts>_state_reset.md` audit. CB resets to FULL.
4. Set `BROKER_PAPER=alpaca` in the cloud routine env.
5. Wait for the next end_of_day routine. First new ENTRY signals will land on
   Alpaca for real; the log will record broker fill prices + slippage vs sim.

### Verification after enablement

- `scripts/sync_alpaca_state.py` should print "in sync" each day.
- EOD step 8a runs `lib.paper_sim.reconcile()` + the broker-mirror check; any
  divergence triggers an URGENT Telegram alert.
- Log rows in `trades/paper/log.csv` will have `broker_fill=` and `slippage_vs_sim=`
  values in the `notes` column when mirror mode is active.

### Reverting

- Set `BROKER_PAPER=sim` (or unset) in the cloud routine env.
- Existing Alpaca positions remain on the broker until you close them manually
  or run `--reset-fresh-start` again.
- The local sim state continues from where it was — won't match Alpaca anymore,
  but that's the expected outcome of leaving mirror mode.
