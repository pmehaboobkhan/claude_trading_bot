routine: weekly_review
started_at: '2026-05-17T00:54:07Z'
ended_at: '2026-05-17T00:59:12Z'
duration_seconds: 305.0
exit_reason: clean
approximate_input_kb: 183
total_subagent_dispatches: 1
subagent_dispatches:
  compliance_safety: 1
  performance_review: 0
  self_learning: 0
files_read:
- path: config/approved_modes.yaml
  bytes: 1350
- path: config/risk_limits.yaml
  bytes: 5533
- path: prompts/routines/weekly_review.md
  bytes: 6932
- path: .claude/agents/orchestrator.md
  bytes: 4241
- path: journals/daily/2026-05-12.md
  bytes: 24334
- path: journals/daily/2026-05-13.md
  bytes: 50940
- path: journals/daily/2026-05-14.md
  bytes: 45471
- path: journals/daily/2026-05-15.md
  bytes: 13745
- path: trades/paper/log.csv
  bytes: 1566
- path: trades/paper/positions.json
  bytes: 3
- path: journals/weekly/2026-20.md
  bytes: 13985
- path: reports/learning/weekly_learning_review_2026-05-15.md
  bytes: 10763
- path: memory/strategy_lessons/2026-w20.md
  bytes: 2435
- path: reports/weekly_digest/2026-20.md
  bytes: 3004
- path: logs/routine_runs/2026-05-15_190750_weekly_review_audit.md
  bytes: 1720
- path: logs/routine_runs/2026-05-16_130750_weekly_review_audit.md
  bytes: 1841
- path: logs/routine_runs/2026-05-17_005407_start.md
  bytes: 105
artifacts_written:
- logs/routine_runs/2026-05-16_130749_start.md
- logs/routine_runs/2026-05-17_005407_start.md
- logs/routine_runs/2026-05-17_<ts>_weekly_review_audit.md
commits: []
notes: "Third invocation of weekly_review for 2026-W20. Prior runs (2026-05-15T19:07Z\
  \ commit fd72c8c and 2026-05-16T13:07Z commit 44924b1) produced all artifacts: journal,\
  \ learning-review, strategy-lessons, digest, Telegram. This run: schema validation\
  \ PASS; compliance_safety APPROVED; human-attention flag raised re: BROKER_PAPER=alpaca\
  \ 'go live' plan on 2026-05-18 (mode remains PAPER_TRADING; operator gate intact).\
  \ N=1 closed trade (CSCO +618.90); period return +0.82%; max-DD -0.11%; STAY_PAPER.\
  \ max_self_learning_proposals_per_cycle=0 \u2192 no proposed_updates written."
