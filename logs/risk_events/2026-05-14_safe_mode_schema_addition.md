# Risk event — schema-level addition of SAFE_MODE

- timestamp: 2026-05-14T07:00Z
- type: schema_extension
- actor: human (treating this session as the PR review)

## What

Adding `SAFE_MODE` to the `mode` enum of `tests/schemas/approved_modes.schema.json`
and updating the transitions-documentation comment block in
`config/approved_modes.yaml`. The actual `mode:` field stays `PAPER_TRADING` —
no operational mode change occurs.

## Why

Plan #4 (SAFE_MODE) is being applied: a sixth operating mode that runs the
deterministic engine while suppressing learning writes. Used when prompts
misbehave, model providers degrade, or memory has accumulated low-quality
heuristics. The schema enum must include `SAFE_MODE` so a future operator
flip from PAPER_TRADING to SAFE_MODE schema-validates.

## Why paired risk_events entry

Hook #11 (`halt_audit.sh`) blocks edits to `config/approved_modes.yaml`
unless a `logs/risk_events/*` file was created within the last 10 minutes
in the same session. The hook's intent is to enforce audit-trail pairing on
ALL mode changes including comment-only edits to the transitions block.
This file satisfies that contract.

## Acceptance

- `tests/schemas/approved_modes.schema.json` extended to include SAFE_MODE.
- `config/approved_modes.yaml` transitions comment block describes the
  legal entry/exit paths for SAFE_MODE.
- `mode:` field unchanged (PAPER_TRADING).
- `python3 tests/run_schema_validation.py` passes.
- No new operational behavior — the mode is opt-in via `/enter-safe-mode`
  (added in Plan #4 Task 7).
