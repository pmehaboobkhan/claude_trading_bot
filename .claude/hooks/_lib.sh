#!/usr/bin/env bash
# Shared helpers for hooks. Source this from each hook script.
# Hooks receive a JSON payload on stdin describing the tool call.

set -euo pipefail

# Read stdin once into HOOK_INPUT so multiple helpers can use it.
read_hook_input() {
  if [ -z "${HOOK_INPUT:-}" ]; then
    HOOK_INPUT="$(cat)"
    export HOOK_INPUT
  fi
}

# Use Python for robust JSON parsing (no jq dependency).
hook_field() {
  local path="$1"
  python3 -c '
import json, sys
data = json.loads(sys.stdin.read())
parts = sys.argv[1].split(".")
cur = data
for p in parts:
    if isinstance(cur, dict) and p in cur:
        cur = cur[p]
    else:
        sys.exit(0)
print(cur if not isinstance(cur, (dict, list)) else json.dumps(cur))
' "$path" <<< "$HOOK_INPUT"
}

block() {
  echo "HOOK BLOCK: $*" >&2
  exit 2  # exit 2 = block (Claude Code convention)
}

allow() {
  exit 0
}

repo_root() {
  # Try git first; fall back to current dir if not in a repo.
  git rev-parse --show-toplevel 2>/dev/null || pwd
}
