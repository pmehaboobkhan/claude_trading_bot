#!/usr/bin/env bash
# Enforce append-only on:
#   - trades/paper/log.csv
#   - trades/paper/circuit_breaker_history.jsonl
#   - decisions/by_symbol/*.md
# A change is "append-only" iff the existing file content is a strict prefix
# of the new content. Edit/MultiEdit on these files is rejected entirely
# (those are inherently non-append). Write is allowed only for strict appends.
source "$(dirname "$0")/_lib.sh"
read_hook_input

tool_name="$(hook_field tool_name)"
file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

is_append_only_file=false
case "$file_path" in
  *trades/paper/log.csv|*trades/paper/circuit_breaker_history.jsonl|*decisions/by_symbol/*.md) is_append_only_file=true ;;
esac
$is_append_only_file || allow

# For Edit / MultiEdit: reject — these tools mutate existing content.
case "$tool_name" in
  Edit|MultiEdit)
    block "$file_path is append-only. Use Write with strict-prefix new content."
    ;;
esac

# Write tool: verify new_content starts with the existing file content.
if [ ! -f "$file_path" ]; then
  allow  # first write creates the file
fi
new_content="$(hook_field tool_input.content)"
existing="$(cat "$file_path")"
case "$new_content" in
  "$existing"*) allow ;;
  *) block "$file_path is append-only and the proposed content does not start with the current content. Edits to existing rows are forbidden." ;;
esac
