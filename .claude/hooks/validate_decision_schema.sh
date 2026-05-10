#!/usr/bin/env bash
# After Edit/Write of decisions/<date>/*.json, validate against trade_decision schema.
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

case "$file_path" in
  *decisions/*/*.json)
    cd "$(repo_root)"
    if ! python3 tests/run_schema_validation.py "$file_path"; then
      block "trade_decision schema validation failed for $file_path. Fix and retry."
    fi
    ;;
esac

allow
