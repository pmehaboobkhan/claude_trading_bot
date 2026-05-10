#!/usr/bin/env bash
# Block direct edits to production agent definitions and routine prompts.
# These must go through prompts/proposed_updates/ and a human PR.
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

case "$file_path" in
  *.claude/agents/*.md|*prompts/routines/*.md|*prompts/agents/*.md)
    block "production prompt $file_path is locked. Draft changes in prompts/proposed_updates/ and open a PR."
    ;;
esac

allow
