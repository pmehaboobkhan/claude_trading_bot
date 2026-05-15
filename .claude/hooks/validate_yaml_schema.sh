#!/usr/bin/env bash
# After Edit/Write of any config/*.yaml, validate it against its schema.
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

case "$file_path" in
  *config/*.yaml)
    cd "$(repo_root)"
    # Prefer project venv when present for jsonschema availability;
    # fall back to system python3 for portability.
    PY="$(repo_root)/.venv/bin/python"
    [ -x "$PY" ] || PY=python3
    if ! "$PY" tests/run_schema_validation.py "$file_path"; then
      block "schema validation failed for $file_path. Fix and retry."
    fi
    ;;
esac

allow
