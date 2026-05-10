#!/usr/bin/env bash
# Block Bash calls to broker URLs unless mode permits. Specifically:
#   - paper-api.alpaca.markets allowed only when mode in {PAPER_TRADING, LIVE_PROPOSALS, LIVE_EXECUTION}
#   - api.alpaca.markets        allowed only when mode == LIVE_EXECUTION
source "$(dirname "$0")/_lib.sh"
read_hook_input

cmd="$(hook_field tool_input.command)"
[ -z "$cmd" ] && allow

mode_file="$(repo_root)/config/approved_modes.yaml"
mode=""
if [ -f "$mode_file" ]; then
  mode="$(python3 -c 'import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get("mode",""))' "$mode_file")"
fi

case "$cmd" in
  *"api.alpaca.markets"*)
    case "$cmd" in
      *"paper-api.alpaca.markets"*)
        # paper API
        case "$mode" in
          PAPER_TRADING|LIVE_PROPOSALS|LIVE_EXECUTION) allow ;;
          *) block "paper broker call blocked while mode=$mode (require PAPER_TRADING+)" ;;
        esac
        ;;
      *)
        # live API
        if [ "$mode" != "LIVE_EXECUTION" ]; then
          block "live broker call blocked while mode=$mode (require LIVE_EXECUTION)"
        fi
        ;;
    esac
    ;;
esac

allow
