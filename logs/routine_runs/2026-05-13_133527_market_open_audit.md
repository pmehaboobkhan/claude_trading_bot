routine: market_open
started_at: '2026-05-13T13:35:27+00:00'
ended_at: '2026-05-13T13:43:35.208023+00:00'
duration_seconds: 488.21
exit_reason: clean
approximate_input_kb: 111
total_subagent_dispatches: 0
subagent_dispatches: {}
files_read:
- path: CLAUDE.md
  bytes: 8231
- path: config/approved_modes.yaml
  bytes: 1145
- path: trades/paper/positions.json
  bytes: 1253
- path: trades/paper/circuit_breaker.json
  bytes: 140
- path: trades/paper/log.csv
  bytes: 1014
- path: reports/pre_market/2026-05-13.md
  bytes: 14554
- path: journals/daily/2026-05-12.md
  bytes: 24334
- path: journals/daily/2026-05-13.md
  bytes: 14103
- path: lib/broker.py
  bytes: 5658
- path: lib/data.py
  bytes: 4163
- path: lib/paper_sim.py
  bytes: 7640
- path: lib/portfolio_risk.py
  bytes: 9285
- path: lib/portfolio_health.py
  bytes: 4576
- path: lib/routine_audit.py
  bytes: 4981
- path: lib/notify.py
  bytes: 9208
- path: logs/risk_events/2026-05-11_183756_mode_flip_paper_trading.md
  bytes: 2932
- path: logs/routine_runs/2026-05-13_103325_pre_market_audit.md
  bytes: 1449
artifacts_written:
- journals/daily/2026-05-13.md
- logs/risk_events/2026-05-13_134137_circuit_breaker.md
- trades/paper/circuit_breaker.json
commits: []
notes: "CB transitioned HALF -> OUT on paper_sim-only equity $100,655.08 vs known-inflated\
  \ persisted peak $119,140.25 (drawdown 15.52% > out_dd 12%). Transition is artifact-driven\
  \ (broker-vs-paper_sim cash double-count from 2026-05-12 EOD); operational impact\
  \ nil for this monitoring routine (no opens, EXITs not throttled, no invalidations\
  \ triggered). 5 positions unchanged, +$629.55 unrealized (+1.63%). Reconcile PASS.\
  \ Live IEX quotes fresh (sub-second) \u2014 feed asymmetry vs 19-day-stale daily\
  \ bars from pre-market. Earlier 13:37Z market_open invocation (commit 3a944dc) transitioned\
  \ FULL->HALF on broker-derived equity but omitted journal+risk_event entries; this\
  \ run cleans up the audit trail and writes the second transition properly. New lesson-pending:\
  \ market_open must write journal+risk_event+reconcile atomically with CB state change.\
  \ Escalated lesson-pending: CB equity-source fix is now must-fix-before-EOD."
