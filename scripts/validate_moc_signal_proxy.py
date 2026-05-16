"""MOC signal-proxy validation harness (Option B validation gate).

Option B submits Market-On-Close orders, so fills land at the official close —
the exact price the backtest assumes (`lib.backtest` fills at
`bars[-1]["close"]`). The only thing that differs from the validated backtest
is the *signal input*: live computes signals at ~15:50 ET using the then-
current price as a stand-in for "today's close", whereas the backtest used the
true 16:00 close.

This harness measures the only thing that can therefore differ: **does using
the ~15:50 price as the last bar change the decision** (ENTRY/EXIT set, plus
the regime label that gates several strategies) versus using the true close.

`decision_divergence` is the pure comparison core (no I/O); the data fetch and
report writing are layered on top in later functions.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib import config, data, signals  # noqa: E402

_ET = ZoneInfo("America/New_York")


def substitute_last_close(bars: list[dict], proxy_price: float) -> list[dict]:
    """Return a copy of `bars` with the last bar's close set to `proxy_price`.

    All prior bars (official daily closes) are untouched — only the most
    recent bar becomes the ~15:50 proxy. High/low are widened if needed so the
    bar stays internally consistent (close never outside [low, high]). The
    input is not mutated.
    """
    if not bars:
        raise ValueError("cannot substitute last close on an empty bar list")
    price = float(proxy_price)
    last = dict(bars[-1])
    last["close"] = price
    last["high"] = max(last["high"], price)
    last["low"] = min(last["low"], price)
    return list(bars[:-1]) + [last]


def build_per_day(daily_by_sym: dict[str, list[dict]],
                  proxy_by_day: dict[str, dict[str, float]],
                  watchlist_symbols: list[str], strategy_rules: dict,
                  strategy_params: dict | None = None) -> list[dict]:
    """For each sample day (a key of `proxy_by_day`), reconstruct the bar
    history as it stood that day and compare the true-close decision vs the
    ~15:50-proxy decision.

    `daily_by_sym[sym]` is the full daily series (official closes). For day D
    the history is truncated to bars dated <= D; the proxy history is the same
    with that day's last close swapped for the intraday proxy price.
    """
    results: list[dict] = []
    for day in sorted(proxy_by_day):
        bars_close: dict[str, list[dict]] = {}
        bars_proxy: dict[str, list[dict]] = {}
        for sym in watchlist_symbols:
            trunc = [b for b in daily_by_sym.get(sym, [])
                     if b["ts"][:10] <= day]
            bars_close[sym] = trunc
            pp = proxy_by_day[day].get(sym)
            bars_proxy[sym] = (
                substitute_last_close(trunc, pp)
                if pp is not None and trunc else trunc
            )
        res = dict(decision_divergence(
            bars_close, bars_proxy, watchlist_symbols, strategy_rules,
            strategy_params))
        res["date"] = day
        results.append(res)
    return results


def summarize(per_day: list[dict], *, min_agreement_rate: float = 0.99) -> dict:
    """Aggregate per-day `decision_divergence` results into a gate verdict.

    The verdict is a recommendation input only — per the proposal, human PR
    approval is still required and every divergent day must be inspected for
    whether the true-close decision was itself borderline. `summarize` does
    not auto-classify borderline-ness; it surfaces every divergence for that
    manual review.
    """
    total = len(per_day)
    if total == 0:
        return {
            "total_days": 0, "agreeing_days": 0, "agreement_rate": 0.0,
            "verdict": "FAIL",
            "reasons": ["no sample — zero days evaluated; cannot validate"],
            "divergent_days": [], "per_strategy_divergences": {},
            "regime_flip_days": 0, "min_agreement_rate": min_agreement_rate,
        }

    agreeing = [d for d in per_day if d.get("agree")]
    rate = round(len(agreeing) / total, 4)
    divergent_days = [
        {"date": d.get("date"), "divergences": d.get("divergences", []),
         "regime_close": d.get("regime_close"),
         "regime_proxy": d.get("regime_proxy")}
        for d in per_day if not d.get("agree")
    ]
    per_strategy: Counter = Counter()
    for d in divergent_days:
        for div in d["divergences"]:
            per_strategy[div["strategy"]] += 1
    regime_flip_days = sum(
        1 for d in per_day
        if d.get("regime_close") != d.get("regime_proxy"))

    reasons: list[str] = []
    verdict = "PASS" if rate >= min_agreement_rate else "FAIL"
    if verdict == "FAIL":
        reasons.append(
            f"agreement_rate {rate:.4f} < required {min_agreement_rate}")
    if regime_flip_days:
        reasons.append(
            f"{regime_flip_days} day(s) had a regime-label flip — inspect each")

    return {
        "total_days": total, "agreeing_days": len(agreeing),
        "agreement_rate": rate, "verdict": verdict, "reasons": reasons,
        "divergent_days": divergent_days,
        "per_strategy_divergences": dict(per_strategy),
        "regime_flip_days": regime_flip_days,
        "min_agreement_rate": min_agreement_rate,
    }


def _actionable(sigs: list) -> dict[tuple[str, str], str]:
    """Reduce a Signal list to the decisions a routine acts on.

    Only ENTRY/EXIT are trades; HOLD/NO_SIGNAL are no-ops and are treated as
    "NONE" (absence) so a HOLD vs NO_SIGNAL wording change is not a divergence.
    """
    out: dict[tuple[str, str], str] = {}
    for s in sigs:
        if s.action in ("ENTRY", "EXIT"):
            out[(s.strategy, s.symbol)] = s.action
    return out


def decision_divergence(bars_close: dict, bars_proxy: dict,
                        watchlist_symbols: list[str], strategy_rules: dict,
                        strategy_params: dict | None = None) -> dict:
    """Compare the decisions produced from the true-close history vs the
    ~15:50-proxy history.

    Returns a dict with `agree` (identical actionable decisions AND identical
    regime label), the per-(strategy,symbol) `divergences`, and both regime
    labels. A regime flip alone counts as a divergence because the regime
    gates strategy behaviour downstream.
    """
    def run(bars: dict) -> tuple[dict, str]:
        regime = signals.detect_regime(bars.get("SPY", []), None)
        sigs = signals.evaluate_all(
            bars, watchlist_symbols, regime, strategy_rules, strategy_params,
        )
        return _actionable(sigs), regime.regime

    close_map, regime_close = run(bars_close)
    proxy_map, regime_proxy = run(bars_proxy)

    divergences: list[dict] = []
    for strat, sym in sorted(set(close_map) | set(proxy_map)):
        ca = close_map.get((strat, sym), "NONE")
        pa = proxy_map.get((strat, sym), "NONE")
        if ca != pa:
            divergences.append({
                "strategy": strat, "symbol": sym,
                "close_action": ca, "proxy_action": pa,
            })

    agree = not divergences and regime_close == regime_proxy
    return {
        "agree": agree,
        "regime_close": regime_close,
        "regime_proxy": regime_proxy,
        "close_actions": sorted(
            f"{s}:{sym}={a}" for (s, sym), a in close_map.items()),
        "proxy_actions": sorted(
            f"{s}:{sym}={a}" for (s, sym), a in proxy_map.items()),
        "divergences": divergences,
    }


# ---------------------------------------------------------------------------
# Network + report shell (thin glue around the tested cores above). This is
# the operator-run gate: its verdict is a RECOMMENDATION INPUT only — human PR
# approval is still required before Option B can be enabled (see
# prompts/proposed_updates/2026-05-15_moc_close_execution.md).
# ---------------------------------------------------------------------------


def fetch_daily(symbols: list[str], *, limit: int = 400) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for sym in symbols:
        try:
            out[sym] = data.get_bars(sym, timeframe="1Day", limit=limit)
        except Exception as exc:  # noqa: BLE001 - external boundary; report + continue
            print(f"[warn] daily fetch failed {sym}: {exc}", file=sys.stderr)
            out[sym] = []
    return out


def fetch_intraday_proxy(symbols: list[str], *, period: str = "60d",
                         interval: str = "30m",
                         cutoff_hhmm: str = "15:50") -> dict[str, dict[str, float]]:
    """proxy_by_day[YYYY-MM-DD][sym] = last intraday close at/before the ET
    cutoff that day. yfinance directly: lib.data routes intraday to Alpaca
    (keyed, short free history); the gate needs free ~60d intraday."""
    import yfinance as yf
    cut_h, cut_m = (int(x) for x in cutoff_hhmm.split(":"))
    proxy: dict[str, dict[str, float]] = {}
    for sym in symbols:
        try:
            df = yf.download(sym, period=period, interval=interval,
                             progress=False, auto_adjust=True, threads=False)
        except Exception as exc:  # noqa: BLE001 - external boundary
            print(f"[warn] intraday fetch failed {sym}: {exc}", file=sys.stderr)
            continue
        if df.empty:
            continue
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        for ts, row in df.iterrows():
            pyts = ts.to_pydatetime()
            if pyts.tzinfo is None:
                pyts = pyts.replace(tzinfo=UTC)
            et = pyts.astimezone(_ET)
            if (et.hour, et.minute) > (cut_h, cut_m):
                continue
            day = et.strftime("%Y-%m-%d")
            proxy.setdefault(day, {})[sym] = float(row["Close"])
    return proxy


def render_report(summary: dict, *, interval: str, period: str,
                  cutoff: str) -> str:
    s = summary
    lines = [
        f"# MOC signal-proxy validation — {datetime.now(UTC):%Y-%m-%d}",
        "",
        "**Option B gate (Approach A: empirical decision-agreement).** "
        "Fills are unaffected (MOC = official close = backtest assumption); "
        "this measures only whether a ~15:50 signal input changes the "
        "decision vs the true 16:00 close.",
        "",
        f"- Sample: last `{period}` of `{interval}` bars; proxy = last "
        f"intraday close at/before **{cutoff} ET** (a conservative upper "
        "bound — the real 15:50 proxy is closer to the close than this).",
        f"- Days evaluated: **{s['total_days']}**",
        f"- Decision-agreement rate: **{s['agreement_rate']:.4f}** "
        f"(threshold {s['min_agreement_rate']})",
        f"- Regime-flip days: **{s['regime_flip_days']}**",
        f"- Per-strategy divergences: `{s['per_strategy_divergences']}`",
        "",
        f"## Provisional verdict: **{s['verdict']}**",
        "",
        "> Recommendation input only. Human PR approval is still required, "
        "and every divergent day below must be inspected for whether the "
        "true-close decision was itself borderline (a borderline flip is not "
        "a methodology failure — it resolves the same way live).",
        "",
    ]
    if s["reasons"]:
        lines += ["### Reasons", *[f"- {r}" for r in s["reasons"]], ""]
    if s["divergent_days"]:
        lines += ["### Divergent days (manual borderline review required)", ""]
        for d in s["divergent_days"]:
            lines.append(
                f"- **{d['date']}** regime {d['regime_close']}→"
                f"{d['regime_proxy']}; {d['divergences']}")
    else:
        lines.append("No divergent days in the sample.")
    lines += [
        "",
        "### Analytical sanity bound (Approach B)",
        "The strategies are low-frequency: `dual_momentum_taa` uses a ~210-day "
        "SMA trend filter, `large_cap_momentum_top5` ranks by ~126-day "
        "return, `gold_permanent_overlay` is price-insensitive. A ~10-minute "
        "last-bar move shifts a 210-day SMA by ≈Δ/210 and a 126-day return by "
        "a comparably tiny amount, so a decision can only flip when it was "
        "already on a knife-edge at the true close — i.e. resolves the same "
        "way live. The empirical rate above quantifies how often that "
        "knife-edge actually occurs.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Option B MOC signal-proxy validation gate")
    ap.add_argument("--symbols", help="comma-separated; default = watchlist")
    ap.add_argument("--max-symbols", type=int, default=0,
                    help="cap symbol count (smoke runs); 0 = no cap")
    ap.add_argument("--period", default="60d")
    ap.add_argument("--interval", default="30m")
    ap.add_argument("--cutoff", default="15:50", help="ET HH:MM proxy cutoff")
    ap.add_argument("--min-agreement", type=float, default=0.99)
    ap.add_argument("--daily-limit", type=int, default=400)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print verdict; do NOT write the report")
    args = ap.parse_args(argv)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = [s["symbol"] for s in config.watchlist()["symbols"]]
    if args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]

    print(f"[gate] {len(symbols)} symbols; intraday {args.period}/"
          f"{args.interval} cutoff {args.cutoff} ET", file=sys.stderr)
    daily = fetch_daily(symbols, limit=args.daily_limit)
    proxy = fetch_intraday_proxy(symbols, period=args.period,
                                 interval=args.interval,
                                 cutoff_hhmm=args.cutoff)
    per_day = build_per_day(daily, proxy, symbols, config.strategy_rules())
    summary = summarize(per_day, min_agreement_rate=args.min_agreement)
    report = render_report(summary, interval=args.interval,
                           period=args.period, cutoff=args.cutoff)

    print(report)
    if not args.dry_run:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        out_dir = _REPO_ROOT / "reports" / "learning"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"moc_signal_proxy_validation_{stamp}.md").write_text(
            report, encoding="utf-8")
        (out_dir / f"moc_signal_proxy_validation_{stamp}.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[gate] report written to reports/learning/"
              f"moc_signal_proxy_validation_{stamp}.md", file=sys.stderr)

    # Verdict is advisory; non-zero exit on FAIL so it can gate a CI step.
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
