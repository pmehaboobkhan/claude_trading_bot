routine: weekly_review
started_at: '2026-05-16T13:07:50Z'
ended_at: '2026-05-16T14:10:00Z'
duration_seconds: 3730.0
exit_reason: clean
approximate_input_kb: 177
total_subagent_dispatches: 1
subagent_dispatches:
  performance_review: 0
  self_learning: 0
  compliance_safety: 1
files_read:
- path: config/approved_modes.yaml
  bytes: 1350
- path: config/risk_limits.yaml
  bytes: 5533
- path: prompts/routines/weekly_review.md
  bytes: 6932
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
artifacts_written:
- logs/routine_runs/2026-05-16_130750_start.md
- logs/routine_runs/2026-05-16_130750_weekly_review_audit.md
commits:
- 44924b1
notes: "Saturday-scheduled weekly review for 2026-W20; prior run (2026-05-15T19:07Z,\
  \ commit fd72c8c) produced all artifacts \u2014 journal, learning-review, strategy-lessons,\
  \ digest. Today: compliance_safety gate re-run \u2192 APPROVED; Telegram delivery;\
  \ routine audit for this invocation. N=1 closed trade (CSCO +618.90); period return\
  \ +0.82%; max-DD -0.11%; STAY_PAPER. Prior run inline coverage: performance_review\
  \ (0 separate dispatches, inline) and self_learning (0, inline \u2014 max_self_learning_proposals_per_cycle=0,\
  \ memory/strategy_lessons written by prior run); approximate_input_kb=~185 KB."
