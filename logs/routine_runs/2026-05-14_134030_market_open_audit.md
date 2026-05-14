routine: market_open
started_at: '2026-05-14T13:40:30+00:00'
ended_at: '2026-05-14T13:45:10+00:00'
duration_seconds: 240.0
exit_reason: clean
approximate_input_kb: 115
total_subagent_dispatches: 1
subagent_dispatches:
  orchestrator: 1
files_read:
- path: CLAUDE.md
  bytes: 10625
- path: config/approved_modes.yaml
  bytes: 1350
- path: prompts/routines/market_open.md
  bytes: 8518
- path: trades/paper/positions.json
  bytes: 1003
- path: trades/paper/circuit_breaker.json
  bytes: 140
- path: trades/paper/log.csv
  bytes: 1301
- path: reports/pre_market/2026-05-14.md
  bytes: 18452
- path: journals/daily/2026-05-14.md
  bytes: 4909
- path: journals/daily/2026-05-13.md
  bytes: 50940
- path: logs/risk_events/2026-05-14_133948_circuit_breaker.md
  bytes: 2171
- path: logs/routine_runs/2026-05-14_133529_market_open_audit.md
  bytes: 1045
- path: data/market/2026-05-14/0630.json
  bytes: 17766
artifacts_written:
- trades/paper/circuit_breaker.json
- logs/risk_events/2026-05-14_134109_cb_artifact_rollback.md
- logs/risk_events/2026-05-14_133948_circuit_breaker.md
- journals/daily/2026-05-14.md
commits:
- dbe22b2
notes: 'Rollback run: identified broker-cash double-count bug in prior orchestrator
  invocation that falsely advanced CB OUT->FULL. Reverted CB JSON via git checkout,
  recomputed paper_sim equity correctly ($100,605.39), re-ran portfolio_risk.advance()
  with no transition. Deleted bogus circuit_breaker_history.jsonl. CB state remains
  OUT (correctly). 4 positions checked, 0 closes, 0 new entries. CB equity-source
  fix elevated to action-required.'
