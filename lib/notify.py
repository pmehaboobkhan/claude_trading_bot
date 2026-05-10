"""Telegram notification wrapper.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from env. Never logs the token.
Failures are non-fatal — the routine still commits its artifacts; the absence
of a notification is logged to logs/routine_runs/.
"""
from __future__ import annotations

import logging
import os
from typing import Final

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API: Final = "https://api.telegram.org"


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
