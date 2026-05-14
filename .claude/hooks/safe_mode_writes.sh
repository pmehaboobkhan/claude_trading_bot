#!/usr/bin/env bash
# Block writes to memory/ (except memory/daily_snapshots/) and to
# prompts/proposed_updates/ when approved_modes.yaml mode == SAFE_MODE.
# This is the file-layer twin of lib/operating_mode.is_writable().
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

mode_file="$(repo_root)/config/approved_modes.yaml"
[ ! -f "$mode_file" ] && allow

mode="$(python3 -c 'import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get("mode",""))' "$mode_file")"

if [ "$mode" != "SAFE_MODE" ]; then
  allow
fi

# Normalise path (strip absolute prefix if present).
repo="$(repo_root)"
rel="${file_path#$repo/}"
rel="${rel#./}"

# Carveout: memory/daily_snapshots/ is operational, always allowed.
case "$rel" in
  memory/daily_snapshots/*)
    allow
    ;;
esac

# Block writes under memory/ or prompts/proposed_updates/.
case "$rel" in
  memory/*|prompts/proposed_updates/*)
    block "writes to $rel are suppressed in SAFE_MODE (use HALTED to also stop trading, or PR back to PAPER_TRADING to resume learning)"
    ;;
esac

allow
