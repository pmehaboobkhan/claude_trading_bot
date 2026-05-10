---
description: Operator kill switch. Flips approved_modes.yaml to HALTED with paired audit log.
argument-hint: "<reason>"
---

Halt all trading routines. Reason: `$ARGUMENTS`

Steps (must be done in this order — hook #11 enforces the audit pairing):

1. Write `logs/risk_events/<UTC ISO timestamp>_halt.md` with:
   - `# Halt event`
   - `- Triggered: /halt-trading`
   - `- Reason: $ARGUMENTS`
   - `- Operator: human`
2. Update `config/approved_modes.yaml`:
   - Set `mode: HALTED`.
   - Set `mode_set_at` to the current ISO timestamp.
   - Set `mode_set_by: human`.
   - Set `mode_set_reason: $ARGUMENTS`.
   - Append the change to the `history` list.
3. Notify URGENT via Telegram: "HALTED — reason: $ARGUMENTS".
4. Commit with message: `halt: <reason>`.
5. Print a confirmation in chat including the path to the audit log.

Resume requires a human PR explicitly setting `mode` back to a non-HALTED value. The system will NOT resume itself.
