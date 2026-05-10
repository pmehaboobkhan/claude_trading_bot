# Commit message conventions

> One commit per routine run. Format below. Always include the co-author trailer.

## Format

```
<routine>: <short summary>

<body — optional, used for reviews and risk events>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

## Per-routine subject lines

| Routine | Format |
|---|---|
| Pre-market | `pre-market: research report <YYYY-MM-DD> (N symbols flagged)` |
| Market open | `open: N decisions (P proposals, W watch, X no-trade)` |
| Midday | `midday: position review (Q open, R closed)` |
| Pre-close | `pre-close: N hold, M close decisions` |
| End of day | `eod: journal + perf <YYYY-MM-DD> (PnL ±$X.XX, N trades, win rate W%)` |
| Weekly review | `weekly-review: <YYYY-WW> (win rate W%, profit factor PF, alpha vs SPY +/- X.X%)` |
| Monthly review | `monthly-review: <YYYY-MM> (recommendation: <STAY_PAPER\|PROPOSE_HUMAN_APPROVED_LIVE\|HALT_AND_REVIEW>)` |
| Self-learning | `self-learning: <YYYY-MM-DD> (M observations, K proposals drafted, J rejected)` |
| Halt | `halt: <reason>` |
| Manual journal note | `journal: manual note <YYYY-MM-DD>` |

## Body sections (when relevant)

- `Routine: <name>`
- `Trades: <count and W/L breakdown>`
- `Risk events: <count and links>`
- `Memory updates: <files updated>`
- `Notes: <anything noteworthy>`

## Hard rules

- One commit per routine run. Zero commits if nothing changed.
- Never force-push.
- Never amend a commit that's been pushed.
- Never bypass hooks (`--no-verify`).
- The co-author trailer is mandatory on every machine commit.
