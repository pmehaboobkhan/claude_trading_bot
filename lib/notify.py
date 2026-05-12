"""Telegram notification wrapper.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from env. Never logs the token.
Failures are non-fatal — the routine still commits its artifacts; the absence
of a notification is logged to logs/routine_runs/.

Two transports:
- send(): plain markdown text message (the bulleted summary).
- send_document(): upload a file as a Telegram document attachment. Used to
  deliver reports/journals so the user can read them on the phone without
  hitting GitHub — which 404s on private repos and has merge-timing race
  conditions on public ones.
"""
from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Final

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API: Final = "https://api.telegram.org"
# Telegram's bot API documents 50 MB upload limit. We hard-cap at 5 MB as a
# defense — paper-trading artifacts are markdown and JSON, well under this.
MAX_UPLOAD_BYTES: Final = 5 * 1024 * 1024


class NotifyError(RuntimeError):
    pass


def _token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None


def _chat_id() -> str | None:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip() or None


def send(message: str, *, urgent: bool = False) -> bool:
    """Send a Markdown-formatted Telegram message. Returns True on success.

    Never raises — on failure it logs and returns False so the caller's commit
    still proceeds. Notification absence is itself logged (caller's responsibility).
    """
    token = _token()
    chat = _chat_id()
    if not token or not chat:
        logger.warning("telegram credentials missing — message dropped")
        return False

    prefix = "URGENT " if urgent else ""
    text = f"{prefix}[Calm Turtle]\n{message}"

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {"chat_id": chat, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("telegram send failed: %s", exc)
        return False


def send_document(path: str | Path, *, caption: str | None = None,
                  filename: str | None = None) -> bool:
    """Upload a file to the chat as a Telegram document.

    Used to deliver reports and journals so the user can open them on a phone
    without depending on GitHub (private repos 404 for unauthenticated viewers;
    even public repos race the auto-merge action by ~30 seconds).

    Returns True on success. Like `send()`, never raises — failures are logged
    so the caller's commit/journal still proceeds.

    Args:
        path: file to upload. Must be ≤ MAX_UPLOAD_BYTES (5 MB).
        caption: optional caption (max 1024 chars; Markdown allowed).
        filename: optional display name. Defaults to the basename of `path`.
    """
    token = _token()
    chat = _chat_id()
    if not token or not chat:
        logger.warning("telegram credentials missing — document dropped")
        return False

    p = Path(path)
    if not p.exists() or not p.is_file():
        logger.warning("telegram send_document: file not found %s", p)
        return False
    size = p.stat().st_size
    if size == 0:
        logger.warning("telegram send_document: file is empty %s", p)
        return False
    if size > MAX_UPLOAD_BYTES:
        logger.warning(
            "telegram send_document: file %s is %d bytes, exceeds %d-byte cap",
            p, size, MAX_UPLOAD_BYTES,
        )
        return False

    display_name = filename or p.name
    mime, _ = mimetypes.guess_type(display_name)
    mime = mime or "application/octet-stream"

    url = f"{TELEGRAM_API}/bot{token}/sendDocument"
    data: dict[str, str] = {"chat_id": chat}
    if caption is not None:
        # Telegram caption cap is 1024 chars. Truncate defensively.
        data["caption"] = caption[:1024]
        data["parse_mode"] = "Markdown"

    try:
        with p.open("rb") as f:
            files = {"document": (display_name, f, mime)}
            r = requests.post(url, data=data, files=files, timeout=30)
            r.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("telegram send_document failed for %s: %s", p, exc)
        return False


def send_documents(paths: list[str | Path], *, caption: str | None = None) -> int:
    """Convenience: upload multiple files. `caption` is applied to the FIRST
    document only — subsequent ones are sent uncaptioned to keep the chat clean.

    Returns the count of successfully delivered documents.
    """
    delivered = 0
    for i, p in enumerate(paths):
        ok = send_document(p, caption=caption if i == 0 else None)
        if ok:
            delivered += 1
    return delivered
