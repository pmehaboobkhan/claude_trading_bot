"""Reconcile / reset local paper state against Alpaca paper account.

Two modes:

  --check (default)
    Read both sides and report any divergence. No writes. Exit code 0 if
    in sync, 1 if divergence detected.

  --reset-fresh-start
    DESTRUCTIVE. Cancel all open Alpaca orders, close all Alpaca positions,
    clear the local positions.json (writes a RESET marker row to log.csv
    since the log is append-only), reset trades/paper/circuit_breaker.json
    so peak_equity = current Alpaca equity and state = FULL.

    Use when initially enabling BROKER_PAPER=alpaca mirror mode, or after a
    state-divergence incident. Writes a logs/risk_events/<ts>_state_reset.md
    audit trail.

Usage:
    python3 scripts/sync_alpaca_state.py
    python3 scripts/sync_alpaca_state.py --reset-fresh-start
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib import broker  # noqa: E402
from lib import paper_sim  # noqa: E402

CB_PATH = REPO_ROOT / "trades" / "paper" / "circuit_breaker.json"
RISK_EVENTS_DIR = REPO_ROOT / "logs" / "risk_events"


def _local_positions() -> dict[str, dict]:
    if not paper_sim.POSITIONS_PATH.exists():
        return {}
    return json.loads(paper_sim.POSITIONS_PATH.read_text(encoding="utf-8"))


def _broker_positions() -> dict[str, dict]:
    """Return {symbol: {qty, avg_entry_price}} from Alpaca."""
    out: dict[str, dict] = {}
    for p in broker.get_positions():
        out[p["symbol"]] = {
            "qty": p["qty"],
            "avg_entry_price": p["avg_entry_price"],
            "market_value": p["market_value"],
        }
    return out


def _check() -> int:
    """Compare local positions.json vs Alpaca; print divergence; return 0 if in sync."""
    print("[sync] reading local positions...")
    local = _local_positions()
    print(f"  local: {len(local)} positions: {sorted(local.keys())}")

    print("[sync] reading Alpaca paper account...")
    try:
        snap = broker.account_snapshot()
        bpos = _broker_positions()
    except broker.BrokerError as exc:
        print(f"[sync] FAILED to read broker: {exc}")
        print("       Make sure ALPACA_PAPER_KEY_ID / ALPACA_PAPER_SECRET_KEY are set.")
        return 2
    print(f"  alpaca: {len(bpos)} positions: {sorted(bpos.keys())}")
    print(f"  alpaca equity: ${snap['equity']:,.2f}, cash: ${snap['cash']:,.2f}, "
          f"buying_power: ${snap['buying_power']:,.2f}")

    local_syms = set(local.keys())
    broker_syms = set(bpos.keys())
    only_local = local_syms - broker_syms
    only_broker = broker_syms - local_syms
    in_both = local_syms & broker_syms

    divergences: list[str] = []

    if only_local:
        for s in sorted(only_local):
            divergences.append(f"  - {s}: in local positions but NOT on Alpaca "
                               f"(qty={local[s].get('quantity', '?')})")
    if only_broker:
        for s in sorted(only_broker):
            divergences.append(f"  - {s}: on Alpaca but NOT in local positions "
                               f"(qty={bpos[s]['qty']})")
    for s in sorted(in_both):
        local_qty = local[s].get("quantity", 0)
        broker_qty = bpos[s]["qty"]
        if abs(float(local_qty) - float(broker_qty)) > 1e-6:
            divergences.append(f"  - {s}: qty mismatch (local={local_qty}, "
                               f"alpaca={broker_qty})")

    if not divergences:
        print("[sync] in sync — local and Alpaca match.")
        return 0

    print(f"[sync] {len(divergences)} divergence(s):")
    for d in divergences:
        print(d)
    print("\n[sync] To resolve: re-run with --reset-fresh-start to clear both sides "
          "and start clean.")
    return 1


def _reset_fresh_start() -> int:
    """Cancel orders, close positions on Alpaca; clear local; reset CB."""
    print("[reset] === fresh-start sequence ===")

    # 1. Read pre-state for the audit log
    try:
        snap_before = broker.account_snapshot()
        bpos_before = _broker_positions()
    except broker.BrokerError as exc:
        print(f"[reset] FAILED to read broker: {exc}")
        return 2

    local_before = _local_positions()
    cb_before = json.loads(CB_PATH.read_text(encoding="utf-8")) if CB_PATH.exists() else {}

    print(f"[reset] before: alpaca equity=${snap_before['equity']:,.2f}, "
          f"alpaca positions={len(bpos_before)}, local positions={len(local_before)}, "
          f"cb_state={cb_before.get('state', '?')}, cb_peak=${cb_before.get('peak_equity', 0):,.2f}")

    # 2. Cancel all open Alpaca orders + close all Alpaca positions
    print("[reset] canceling open Alpaca orders...")
    n_canceled = broker.cancel_all_open_orders()
    print(f"  canceled {n_canceled} order(s)")

    if bpos_before:
        print(f"[reset] closing {len(bpos_before)} Alpaca position(s)...")
        closes = broker.close_all_positions(cancel_orders=True)
        print(f"  submitted {len(closes)} close order(s)")
    else:
        print("[reset] no Alpaca positions to close")

    # 3. Clear local positions.json
    print("[reset] clearing local positions.json...")
    paper_sim.POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    paper_sim.POSITIONS_PATH.write_text("{}\n", encoding="utf-8")

    # 4. Append RESET marker to log.csv (append-only; can't truncate)
    print("[reset] appending RESET marker to log.csv...")
    paper_sim._ensure_log()
    reset_ts = datetime.now(UTC).isoformat()
    with paper_sim.LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            reset_ts, "_RESET_", "RESET", 0, 0, "scripts/sync_alpaca_state.py",
            "", "", "RESET", 0,
            (f"sync_alpaca_state --reset-fresh-start; "
             f"local_before={len(local_before)} positions, "
             f"alpaca_before={len(bpos_before)} positions, "
             f"alpaca_equity_before=${snap_before['equity']:,.2f}; "
             f"all subsequent rows are fresh post-reset state"),
        ])

    # 5. Reset CB state — read CURRENT alpaca equity (after closes)
    print("[reset] reading post-close Alpaca equity for new CB peak...")
    snap_after = broker.account_snapshot()
    new_peak = snap_after["equity"]
    new_cb_state = {
        "last_observed_equity": new_peak,
        "peak_equity": new_peak,
        "state": "FULL",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    CB_PATH.write_text(json.dumps(new_cb_state, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(f"  CB reset: state=FULL, peak_equity=${new_peak:,.2f}")

    # 6. Write paired risk_events audit
    risk_event_path = RISK_EVENTS_DIR / f"{datetime.now(UTC):%Y-%m-%d_%H%M%S}_state_reset.md"
    RISK_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    risk_event_path.write_text(_risk_event_text(
        snap_before=snap_before, bpos_before=bpos_before, local_before=local_before,
        cb_before=cb_before, snap_after=snap_after,
        n_canceled=n_canceled, reset_ts=reset_ts,
    ), encoding="utf-8")
    print(f"[reset] audit written: {risk_event_path.relative_to(REPO_ROOT)}")

    print("[reset] === complete ===")
    print(f"[reset] Next: enable mirror mode by setting BROKER_PAPER=alpaca in routine env.")
    return 0


def _risk_event_text(*, snap_before, bpos_before, local_before, cb_before,
                     snap_after, n_canceled, reset_ts) -> str:
    lines = [
        "# Risk event — Alpaca state reset (fresh-start)",
        "",
        f"- timestamp: {reset_ts}",
        "- type: state_reset",
        "- triggered_by: scripts/sync_alpaca_state.py --reset-fresh-start",
        "- actor: human (operator-initiated)",
        "",
        "## Why",
        "Switching from internal CSV simulator (BROKER_PAPER=sim) to Alpaca paper",
        "mirror mode (BROKER_PAPER=alpaca). The local sim had accumulated divergent",
        "state (positions, CB peak) that does not match the Alpaca paper account.",
        "Fresh start ensures local and Alpaca are aligned from this point forward.",
        "",
        "## Before",
        f"- Alpaca equity: ${snap_before['equity']:,.2f}",
        f"- Alpaca cash: ${snap_before['cash']:,.2f}",
        f"- Alpaca positions: {len(bpos_before)}: {sorted(bpos_before.keys())}",
        f"- Local positions.json: {len(local_before)}: {sorted(local_before.keys())}",
        f"- Local CB state: {cb_before.get('state', '?')}, "
        f"peak=${cb_before.get('peak_equity', 0):,.2f}",
        "",
        "## Actions",
        f"- Canceled {n_canceled} open Alpaca order(s)",
        f"- Closed {len(bpos_before)} Alpaca position(s)",
        "- Cleared trades/paper/positions.json (set to {})",
        "- Appended RESET marker row to trades/paper/log.csv (log is append-only;",
        "  all rows BEFORE this marker are pre-reset state)",
        f"- Reset trades/paper/circuit_breaker.json: state=FULL, "
        f"peak_equity=${snap_after['equity']:,.2f}",
        "",
        "## After",
        f"- Alpaca equity: ${snap_after['equity']:,.2f}",
        "- Alpaca positions: 0",
        "- Local positions.json: {}",
        "- Local CB: FULL",
        "",
        "## Operator next steps",
        "- Verify BROKER_PAPER=alpaca is set in the cloud routine env.",
        "- Verify ALPACA_PAPER_KEY_ID / ALPACA_PAPER_SECRET_KEY are set.",
        "- Wait for the next end_of_day routine; first new entries will land on",
        "  Alpaca for real, log captures broker fill prices + slippage.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-fresh-start", action="store_true",
                        help="DESTRUCTIVE: close all Alpaca positions, clear local "
                             "state, reset CB. Use to initialize Alpaca-mirror mode.")
    args = parser.parse_args()

    if args.reset_fresh_start:
        return _reset_fresh_start()
    return _check()


if __name__ == "__main__":
    sys.exit(main())
