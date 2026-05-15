routine: weekly_review
started_at: '2026-05-15T19:07:50Z'
ended_at: '2026-05-15T19:18:00Z'
duration_seconds: 610.0
exit_reason: clean
approximate_input_kb: 175
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
- path: config/strategy_rules.yaml
  bytes: 3803
- path: prompts/routines/weekly_review.md
  bytes: 6932
- path: journals/daily/2026-05-12.md
  bytes: 24334
- path: journals/daily/2026-05-13.md
  bytes: 50940
- path: journals/daily/2026-05-14.md
  bytes: 45471
- path: journals/daily/2026-05-15.md
  bytes: 5843
- path: trades/paper/log.csv
  bytes: 1566
- path: trades/paper/positions.json
  bytes: 3
- path: trades/paper/circuit_breaker.json
  bytes: 139
- path: memory/prediction_reviews/2026-05-12.md
  bytes: 6690
- path: memory/prediction_reviews/2026-05-13.md
  bytes: 6658
- path: memory/prediction_reviews/2026-05-14.md
  bytes: 14249
- path: memory/daily_snapshots/2026-05-14.md
  bytes: 884
- path: decisions/2026-05-13/1536_CSCO.json
  bytes: 5641
artifacts_written:
- journals/weekly/2026-20.md
- reports/learning/weekly_learning_review_2026-05-15.md
- memory/strategy_lessons/2026-w20.md
- reports/weekly_digest/2026-20.md
commits: []
notes: First weekly review; paper trading started 2026-05-12; N=1 closed trade (CSCO
  +618.90); CB peak-inflation bug resolved by reset; max_self_learning_proposals_per_cycle=0
  so no prompts/proposed_updates writes; compliance_safety=APPROVED; duplicate regime_diversity_gates
  block flagged in risk_limits.yaml (pre-existing, not introduced by this run); approximate_input_kb=~220KB
