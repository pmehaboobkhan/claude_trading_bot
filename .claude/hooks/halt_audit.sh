#!/usr/bin/env bash
# Require a paired logs/risk_events/ entry whenever approved_modes.yaml is being written.
# Direct edits to approved_modes.yaml without the audit log are blocked.
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

case "$file_path" in
  *config/approved_modes.yaml|config/approved_modes.yaml)
    risk_dir="$(repo_root)/logs/risk_events"
    if [ ! -d "$risk_dir" ]; then
      block "config/approved_modes.yaml change requires a paired logs/risk_events/<ts>.md entry (logs/risk_events directory not found)"
    fi
    # Look for any risk_event file modified within the last 10 minutes.
    recent=$(find "$risk_dir" -type f -name '*.md' -mmin -10 2>/dev/null | head -n 1)
    if [ -z "$recent" ]; then
      block "config/approved_modes.yaml change requires writing logs/risk_events/<ts>_<reason>.md in the same session first"
    fi
    ;;
esac

allow
