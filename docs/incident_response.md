# Incident Response

> What to do when the system misbehaves, the broker rejects orders, or you suspect a leak. Read it now so you don't read it during an incident.

## Severity tiers

| Tier | Definition | Response time |
|---|---|---|
| SEV-1 | Real money at risk; broker keys may be compromised; system placed an unintended order. | Immediate — halt + rotate keys. |
| SEV-2 | Risk event triggered; daily loss cap breached; agent loop wedged. | Within 1 hour — halt trading, investigate. |
| SEV-3 | Quality issue; bad signal; missed routine. | Same day — fix in next routine cycle. |

## Universal first move

Always run `/halt-trading <reason>` first. The cost of pausing is negligible; the cost of letting a problem compound is not.

## SEV-1 playbook

1. `/halt-trading <reason>` — flips mode to HALTED.
2. **Rotate Alpaca keys** at `app.alpaca.markets`. Old keys are dead immediately.
3. Update the keys in Claude Code routine secrets (and `.env.local` if used).
4. If you suspect a key leak: `git log --all -- '*'` for any commit that might contain a value. If found, contact GitHub support (rotation alone may not be enough — git history is permanent on remotes).
5. File `logs/risk_events/<ts>_sev1.md` with timeline, evidence, and remediation. Commit.
6. Postmortem within 7 days.

## SEV-2 playbook

1. `/halt-trading <reason>`.
2. Investigate `logs/risk_events/`, `logs/routine_runs/` to find the trigger.
3. If a config rule was wrong, open a PR. Don't edit config under pressure — write down what you'd change, sleep on it, then PR.
4. Resume only after root cause is understood.

## SEV-3 playbook

1. Note the issue in today's daily journal under "what failed."
2. Self-Learning will pick it up at the next weekly review.
3. If the same SEV-3 repeats 3+ times, escalate to SEV-2.

## Broker-specific

| Symptom | Diagnosis | Action |
|---|---|---|
| Alpaca returns 401 | Key issue | Rotate. |
| Alpaca returns 422 on submit | Order validation failed (insufficient buying power, bad symbol, etc.) | Fix the trade decision; do not retry blindly. |
| Position discrepancy at EOD reconcile | `lib.paper_sim` vs `trades/paper/log.csv` divergence | Halt. Manually reconcile. Investigate the divergent fill. |

## Data-source incidents

- News connector down → news_unavailable; routines continue with caution flag (already designed).
- Market-data connector down → NO_TRADE for affected symbols; halt routine if > 50% of watchlist affected.
- SEC EDGAR rate-limited → fundamentals stale; non-blocking.

## Communication

- Telegram URGENT message goes out automatically on SEV-1 and SEV-2.
- For SEV-1, also document in the journal and consider a postmortem channel (your choice — Notion / Slack / email).

## Postmortem template

```markdown
# Postmortem — <date> — <one-line summary>

## Timeline (UTC)
- HH:MM — what happened
- HH:MM — what we noticed
- HH:MM — what we did

## Impact
- Real or paper PnL impact.
- Data integrity (reconciliation passed?).
- Trust (was this a "the system did the wrong thing" event, or a "the system did the right thing under bad conditions" event?).

## Root cause
- The actual underlying defect, not the symptom.

## What worked
- Halts, hooks, alerts that fired correctly.

## What didn't
- Halts, hooks, alerts that should have fired and didn't.

## Action items
- [ ] Concrete fix.
- [ ] Test that proves the fix.
- [ ] Memory update.
```
