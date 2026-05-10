#!/usr/bin/env bash
# Block any write to trades/live/* unless approved_modes.yaml mode == LIVE_EXECUTION.
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

case "$file_path" in
  *trades/live/*)
    mode_file="$(repo_root)/config/approved_modes.yaml"
    if [ ! -f "$mode_file" ]; then
      block "trades/live/* write attempted but approved_modes.yaml is missing"
    fi
    mode="$(python3 -c 'import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get("mode",""))' "$mode_file")"
    if [ "$mode" != "LIVE_EXECUTION" ]; then
      block "writes to trades/live/* are blocked while mode=$mode (require LIVE_EXECUTION)"
    fi
    ;;
esac

allow
