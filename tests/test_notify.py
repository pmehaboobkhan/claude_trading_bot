"""Unit tests for lib/notify.py — Telegram text + document delivery.

All network calls are mocked via monkeypatch — tests run offline.

Run with: pytest tests/test_notify.py -v
"""
from __future__ import annotations

import pytest
import requests

from lib import notify


# ---------------------------------------------------------------------------
# Fixtures: stub the Telegram credentials env vars
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_creds(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")


@pytest.fixture
def no_creds(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


# ---------------------------------------------------------------------------
# send() — text messages
# ---------------------------------------------------------------------------

def test_send_returns_false_without_credentials(no_creds) -> None:
    assert notify.send("hello") is False


def test_send_posts_with_markdown_parse_mode(stub_creds, monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["payload"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert notify.send("hi") is True
    assert "/sendMessage" in captured["url"]
    assert captured["payload"]["parse_mode"] == "Markdown"
    assert captured["payload"]["chat_id"] == "999"
    assert "[Calm Turtle]" in captured["payload"]["text"]


def test_send_prepends_urgent_prefix(stub_creds, monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, json=None, **kwargs):
        captured["payload"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.send("emergency", urgent=True)
    assert captured["payload"]["text"].startswith("URGENT ")


def test_send_returns_false_on_http_error(stub_creds, monkeypatch) -> None:
    def fake_post(*a, **kw):
        raise requests.ConnectionError("network unreachable")

    monkeypatch.setattr(notify.requests, "post", fake_post)
    # Must NOT raise — callers depend on this for commit-flow continuity.
    assert notify.send("hi") is False


# ---------------------------------------------------------------------------
# send_document()
# ---------------------------------------------------------------------------

def test_send_document_returns_false_without_credentials(no_creds, tmp_path) -> None:
    f = tmp_path / "report.md"
    f.write_text("body", encoding="utf-8")
    assert notify.send_document(f) is False


def test_send_document_returns_false_when_file_missing(stub_creds, tmp_path) -> None:
    assert notify.send_document(tmp_path / "missing.md") is False


def test_send_document_returns_false_when_file_empty(stub_creds, tmp_path) -> None:
    f = tmp_path / "empty.md"
    f.touch()
    assert notify.send_document(f) is False


def test_send_document_returns_false_when_file_too_big(
    stub_creds, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(notify, "MAX_UPLOAD_BYTES", 100)
    f = tmp_path / "big.md"
    f.write_bytes(b"x" * 200)
    assert notify.send_document(f) is False


def test_send_document_posts_with_correct_payload(
    stub_creds, tmp_path, monkeypatch
) -> None:
    captured: dict = {}

    def fake_post(url, data=None, files=None, **kwargs):
        captured["url"] = url
        captured["data"] = data
        captured["files"] = files
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    f = tmp_path / "pre_market_2026-05-13.md"
    f.write_text("# Pre-market report\nbody", encoding="utf-8")

    assert notify.send_document(f, caption="*Report* attached") is True

    assert "/sendDocument" in captured["url"]
    assert captured["data"]["chat_id"] == "999"
    assert captured["data"]["caption"] == "*Report* attached"
    assert captured["data"]["parse_mode"] == "Markdown"
    assert "document" in captured["files"]
    name, _, mime = captured["files"]["document"]
    assert name == "pre_market_2026-05-13.md"
    assert mime in ("text/markdown", "text/plain", "application/octet-stream")


def test_send_document_truncates_long_caption(
    stub_creds, tmp_path, monkeypatch
) -> None:
    captured: dict = {}

    def fake_post(url, data=None, files=None, **kwargs):
        captured["data"] = data
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    f = tmp_path / "x.md"
    f.write_text("body", encoding="utf-8")
    long_caption = "x" * 2000
    notify.send_document(f, caption=long_caption)
    assert len(captured["data"]["caption"]) == 1024


def test_send_document_omits_caption_when_none(
    stub_creds, tmp_path, monkeypatch
) -> None:
    captured: dict = {}

    def fake_post(url, data=None, files=None, **kwargs):
        captured["data"] = data
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    f = tmp_path / "x.md"
    f.write_text("body", encoding="utf-8")
    notify.send_document(f)
    assert "caption" not in captured["data"]
    assert "parse_mode" not in captured["data"]


def test_send_document_uses_explicit_filename_override(
    stub_creds, tmp_path, monkeypatch
) -> None:
    captured: dict = {}

    def fake_post(url, data=None, files=None, **kwargs):
        captured["files"] = files
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    f = tmp_path / "ugly_temp_name.md"
    f.write_text("body", encoding="utf-8")
    notify.send_document(f, filename="pretty-report.md")
    name, _, _ = captured["files"]["document"]
    assert name == "pretty-report.md"


def test_send_document_returns_false_on_http_error(
    stub_creds, tmp_path, monkeypatch
) -> None:
    f = tmp_path / "x.md"
    f.write_text("body", encoding="utf-8")

    def fake_post(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert notify.send_document(f) is False


# ---------------------------------------------------------------------------
# send_documents() — multi-file convenience
# ---------------------------------------------------------------------------

def test_send_documents_applies_caption_only_to_first(
    stub_creds, tmp_path, monkeypatch
) -> None:
    captured: list[dict] = []

    def fake_post(url, data=None, files=None, **kwargs):
        captured.append({"data": dict(data) if data else None})
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    files = []
    for i, name in enumerate(["report.md", "journal.md", "log.csv"]):
        p = tmp_path / name
        p.write_text(f"file {i}", encoding="utf-8")
        files.append(p)

    delivered = notify.send_documents(files, caption="*EOD* docs")
    assert delivered == 3
    assert captured[0]["data"]["caption"] == "*EOD* docs"
    assert "caption" not in captured[1]["data"]
    assert "caption" not in captured[2]["data"]


def test_send_documents_returns_partial_count_when_some_fail(
    stub_creds, tmp_path, monkeypatch
) -> None:
    f1 = tmp_path / "a.md"
    f1.write_text("a", encoding="utf-8")
    # f2 doesn't exist
    f2 = tmp_path / "missing.md"

    monkeypatch.setattr(
        notify.requests, "post",
        lambda *a, **kw: _FakeResponse(200),
    )
    delivered = notify.send_documents([f1, f2])
    assert delivered == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
