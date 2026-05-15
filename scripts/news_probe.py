"""News-connectivity probe.

The orchestrator should mark symbols `news_unavailable` only when the connector
is truly down — not as a default. Today's pre_market routine has been emitting
`news_unavailable` as a fallback even though midday on 2026-05-14 successfully
fetched news via WebSearch (journals/daily/2026-05-14.md:68). The asymmetry
suggests the routine's "offline" label has become a habit, not a probe result.

This probe makes the call deterministic. It writes a small status file the
orchestrator (and the news_sentiment subagent) can read before deciding
whether to dispatch a full news fetch.

Probe strategy: a single HTTPS HEAD against a high-availability public news
endpoint (SEC EDGAR's homepage). EDGAR is the most authoritative free news
source for SEC filings, has multi-decade uptime, requires no key, and is used
directly by news_sentiment for filings lookups.

Exit codes:
  0 — connector reachable
  1 — connector unreachable (network down / DNS / endpoint 5xx)
  2 — usage error

Writes data/news/<YYYY-MM-DD>/_status.md with the verdict + timestamp + the
exact probe URL used, so routine artifacts cite a source per CLAUDE.md.

Usage:
  python3 scripts/news_probe.py                  # writes status, prints verdict
  python3 scripts/news_probe.py --quiet          # no stdout, exit code only
  python3 scripts/news_probe.py --url <other>    # override probe URL
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROBE_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
PROBE_TIMEOUT_SECONDS = 5.0
USER_AGENT = "calm-turtle-news-probe (mehaboob528@gmail.com)"  # SEC asks for contact


def probe(
    url: str = DEFAULT_PROBE_URL,
    *,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Return (reachable, detail). detail is a short human string for the audit file."""
    # urllib.request usage here is intentional: the URL is operator-controlled
    # (CLI arg or DEFAULT_PROBE_URL constant) and the probe only does HEAD —
    # no payload, no auth, no follow-up GET. Ruff S310 is suppressed accordingly.
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = resp.status
            if 200 <= status < 400:
                return True, f"HTTP {status} from {url}"
            return False, f"HTTP {status} from {url}"
    except urllib.error.HTTPError as exc:
        # Many endpoints reject HEAD with 405 but answer GET fine.
        # Treat 4xx other than network-failure as "reachable" — DNS+TCP+TLS worked.
        if 400 <= exc.code < 500:
            return True, f"HTTP {exc.code} from {url} (HEAD allowed by reachability check)"
        return False, f"HTTP {exc.code} from {url}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"network error: {exc}"


def write_status(*, reachable: bool, detail: str, url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "_status.md"
    now = datetime.now(UTC).isoformat()
    verdict = "REACHABLE" if reachable else "UNREACHABLE"
    body = (
        "# News connector probe\n\n"
        f"- **Verdict:** `{verdict}`\n"
        f"- **Probed (UTC):** {now}\n"
        f"- **URL:** {url}\n"
        f"- **Detail:** {detail}\n\n"
        "Used by `pre_market` / `midday` to decide whether to dispatch the "
        "`news_sentiment` subagent or short-circuit to `news_unavailable`. "
        "Per `CLAUDE.md` the latter is a *risk factor*, never \"no news = bullish.\"\n"
    )
    status_path.write_text(body, encoding="utf-8")
    return status_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_PROBE_URL, help="Probe URL (default: SEC EDGAR)")
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Override the data/news/<date>/ output directory (mainly for tests)",
    )
    args = parser.parse_args(argv)

    reachable, detail = probe(args.url)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "data" / "news" / today
    status_path = write_status(reachable=reachable, detail=detail, url=args.url, out_dir=out_dir)

    if not args.quiet:
        verdict = "REACHABLE" if reachable else "UNREACHABLE"
        try:
            shown_path = status_path.relative_to(REPO_ROOT)
        except ValueError:
            shown_path = status_path
        print(f"[news_probe] {verdict} — {detail}")
        print(f"[news_probe] status -> {shown_path}")

    return 0 if reachable else 1


if __name__ == "__main__":
    sys.exit(main())
