---
description: Enter SAFE_MODE — deterministic engine only, learning suppressed. Writes paired audit log.
argument-hint: "<reason>"
---

Enter SAFE_MODE. Reason: `$ARGUMENTS`

SAFE_MODE keeps the deterministic engine running (signals, paper fills,
circuit-breaker, journals, decisions) but suppresses every kind of
learning write (memory/, prompts/proposed_updates/, self_learning agent
dispatches). Use when the LLM stack needs inspection without halting trading.

Steps (must be done in this order — hook #11 enforces audit pairing):

1. Validate `$ARGUMENTS` is at least 5 characters. If empty / shorter, refuse with:
   "/enter-safe-mode requires a reason of at least 5 characters; refusing."

2. Read `config/approved_modes.yaml`:
   - If current `mode == SAFE_MODE` → print "already in SAFE_MODE since <mode_set_at>" and exit.
   - If current `mode == HALTED` → refuse: "cannot enter SAFE_MODE from HALTED — must transit through PAPER_TRADING via human PR first."
   - If current `mode == LIVE_EXECUTION` → refuse: "cannot enter SAFE_MODE from LIVE_EXECUTION — must transit through PAPER_TRADING via human PR first."
   - If current `mode in (RESEARCH_ONLY, PAPER_TRADING, LIVE_PROPOSALS)` → proceed.

3. Write `logs/risk_events/<UTC ISO timestamp>_safe_mode_entry.md` with:
   - `# SAFE_MODE entry`
   - `- timestamp: <UTC ISO>`
   - `- triggered: /enter-safe-mode`
   - `- reason: $ARGUMENTS`
   - `- operator: human`
   - `- previous_mode: <prev>`
   - `- circuit_breaker_state: <from trades/paper/circuit_breaker.json>`
   - `- open_positions_count: <from trades/paper/positions.json>`

4. Update `config/approved_modes.yaml`:
   - Set `mode: SAFE_MODE`.
   - Set `mode_set_at` to the current ISO timestamp (with offset).
   - Set `mode_set_by: human`.
   - Set `mode_set_reason: $ARGUMENTS`.
   - Append the change to the `history` list.

5. Commit (one commit, both files):
   `safe-mode: entered (reason: <truncated to 60 chars>)`

6. Notify Telegram via `lib.notify.send_html`:
   - Header: `<b>[Calm Turtle] SAFE_MODE entered <YYYY-MM-DD HH:MM ET></b>`
   - `• <b>Reason:</b> <reason>`
   - `• <b>Previous mode:</b> <code>&lt;prev&gt;</code>`
   - `• <b>Trading:</b> paper continues`
   - `• <b>Learning:</b> suppressed`
   - `• <b>Resume requires:</b> human PR back to <code>PAPER_TRADING</code>`
   - `• <b>Audit:</b> <code>logs/risk_events/&lt;filename&gt;</code>`

7. Print confirmation in chat including the path to the audit log.

Constraints:
- DO NOT trigger any subagents during this command.
- DO NOT modify any other config or prompt file.
- The audit log MUST exist in `logs/risk_events/` before `config/approved_modes.yaml` is written — hook #11 enforces this.
- Resume requires a human PR explicitly setting `mode` back to `PAPER_TRADING`.
