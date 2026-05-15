#!/usr/bin/env bash
# Bootstrap script for the scheduled-agent environment.
#
# Installs all Python dependencies pinned in requirements.txt. Idempotent —
# pip skips already-satisfied installs in ~1s. Run this as the FIRST step
# of any scheduled remote-agent routine. The cost is bounded; the alternative
# is silent fallbacks (e.g. yfinance missing → Alpaca IEX with 5-19 day lag).
#
# Usage:
#   scripts/bootstrap_env.sh
#
# Exit codes:
#   0 — all deps satisfied
#   1 — pip failed (network / index / version conflict)
#   2 — Python missing or unsupported version
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[bootstrap] python3 not found on PATH" >&2
  exit 2
fi

PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "[bootstrap] python3 version: $PYVER"

# Verify requirements.txt exists; without it we have no baseline.
if [[ ! -f requirements.txt ]]; then
  echo "[bootstrap] requirements.txt missing — cannot bootstrap" >&2
  exit 1
fi

echo "[bootstrap] installing/verifying dependencies from requirements.txt..."
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt

# Sanity-check the two dependencies most likely to be silently absent in a
# fresh remote-agent env — yfinance powers fresh daily bars, alpaca-py powers
# broker calls. Failing here is louder than a silent fallback later.
python3 - <<'PY'
import sys
missing = []
for mod in ("yfinance", "alpaca"):
    try:
        __import__(mod)
    except ImportError:
        missing.append(mod)
if missing:
    print(f"[bootstrap] FAIL: import check still missing: {missing}", file=sys.stderr)
    sys.exit(1)
print("[bootstrap] import check OK: yfinance + alpaca-py present")
PY

echo "[bootstrap] done"
