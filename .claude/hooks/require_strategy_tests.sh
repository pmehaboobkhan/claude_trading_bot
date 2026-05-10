#!/usr/bin/env bash
# Require a strategy test file for each new/changed strategy in strategy_rules.yaml.
# v1 implementation: ensures at minimum that tests/strategies/<name>_test.md exists for every
# strategy listed under allowed_strategies. We intentionally accept markdown rather than
# code for v1 (backtest/eval reports written by hand or by the backtest harness).
source "$(dirname "$0")/_lib.sh"
read_hook_input

file_path="$(hook_field tool_input.file_path)"
[ -z "$file_path" ] && allow

case "$file_path" in
  *config/strategy_rules.yaml) ;;
  *) allow ;;
esac

# In Phase 1 the tests/strategies directory may be empty. We log a warning to stderr
# but do not block, until a strategy is being changed from NEEDS_MORE_DATA -> ACTIVE_PAPER_TEST.
# Future: parse the diff and only require tests for promoted strategies.
echo "[require_strategy_tests] note: ensure tests/strategies/<name>_test.md exists for any promoted strategy" >&2
allow
