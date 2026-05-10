#!/usr/bin/env bash
# Scan Bash commands for likely-secret patterns. Reject on match.
source "$(dirname "$0")/_lib.sh"
read_hook_input

cmd="$(hook_field tool_input.command)"
[ -z "$cmd" ] && allow

# Patterns: AWS, Alpaca-style key IDs, Telegram bot tokens, JWTs, PEM keys.
# We deliberately keep this narrow to avoid false positives. The broader
# protection is "Claude Code routine secrets are env vars; a key should never
# appear in a Bash command at all." This hook is the last-line defensive net.
patterns=(
  'AKIA[0-9A-Z]{16}'                                                     # AWS access key
  'aws_secret_access_key[[:space:]]*=[[:space:]]*[A-Za-z0-9/+]{40}'      # AWS secret
  'PK[A-Z0-9]{18}'                                                       # Alpaca key id (paper/live)
  'bot[0-9]{6,}:[A-Za-z0-9_-]{30,}'                                      # Telegram bot token
  'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'        # JWT
  'BEGIN[[:space:]]+(RSA|DSA|EC|OPENSSH|PGP)?[[:space:]]*PRIVATE KEY'    # PEM private key (no leading dashes — avoids grep arg parsing)
)

# Allowlist: harmless commands that wouldn't carry secrets.
case "$cmd" in
  *"git "*|*"git-"*|*".sha"*|*"openssl "*) allow ;;
esac

for p in "${patterns[@]}"; do
  if echo "$cmd" | grep -E -q -- "$p"; then
    block "potential secret detected in Bash command (pattern: $p). Refusing."
  fi
done

allow
