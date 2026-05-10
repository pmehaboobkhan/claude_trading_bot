#!/usr/bin/env bash
# Append a routine_run end record. Best-effort; never block.
source "$(dirname "$0")/_lib.sh" 2>/dev/null || true
read_hook_input 2>/dev/null || true

ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
out_dir="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/logs/routine_runs"
mkdir -p "$out_dir" 2>/dev/null || true
file="$out_dir/$(date +%Y-%m-%d)_$(date +%H%M%S)_end.md"
{
  echo "# Routine run end"
  echo "- timestamp: $ts"
  echo "- session_id: $(hook_field session_id 2>/dev/null || echo unknown)"
} > "$file" 2>/dev/null || true

exit 0
