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


# ---------- HTML escape + format helpers ----------

def test_escape_html_escapes_three_special_chars():
    """Telegram HTML mode requires escaping &, <, > — and only those."""
    from lib.notify import escape_html
    assert escape_html("a & b < c > d") == "a &amp; b &lt; c &gt; d"
    # Order matters — & must be escaped first, otherwise &lt; becomes &amp;lt;
    assert escape_html("&lt;") == "&amp;lt;"
    # Underscores, asterisks, brackets all pass through (no Markdown ambiguity)
    assert escape_html("PAPER_TRADING [test]") == "PAPER_TRADING [test]"


def test_format_helpers_produce_html_tags():
    from lib.notify import bold, code, link
    assert bold("Calm Turtle") == "<b>Calm Turtle</b>"
    assert code("PAPER_TRADING") == "<code>PAPER_TRADING</code>"
    assert link("report", "https://example.com/r") == '<a href="https://example.com/r">report</a>'


def test_format_helpers_escape_user_text():
    """Any free text inside helpers must be HTML-escaped to prevent broken markup."""
    from lib.notify import bold, code, link
    assert bold("a & b") == "<b>a &amp; b</b>"
    assert code("if x < y") == "<code>if x &lt; y</code>"
    # Link href is a URL — typically already URL-escaped, but also HTML-attr-escaped
    assert link("a > b", "https://x.test/?q=1&p=2") == '<a href="https://x.test/?q=1&amp;p=2">a &gt; b</a>'


# ---------- send_html() ----------

def test_send_html_uses_html_parse_mode(monkeypatch):
    """send_html must send parse_mode=HTML, not Markdown."""
    from lib import notify
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        class R:
            def raise_for_status(self): pass
        return R()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(notify.requests, "post", fake_post)
    ok = notify.send_html("<b>hi</b>")
    assert ok is True
    assert captured["json"]["parse_mode"] == "HTML"
    assert "<b>hi</b>" in captured["json"]["text"]


def test_send_html_no_credentials_returns_false(monkeypatch):
    from lib import notify
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert notify.send_html("hi") is False


def test_send_html_failure_returns_false(monkeypatch):
    from lib import notify
    import requests as req
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    def fake_post(*a, **kw):
        raise req.RequestException("network down")
    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert notify.send_html("<b>hi</b>") is False


def test_legacy_send_unchanged(monkeypatch):
    """The old send() must still use parse_mode=Markdown (no behavior change yet)."""
    from lib import notify
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        class R:
            def raise_for_status(self): pass
        return R()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.send("*bold*")
    assert captured["json"]["parse_mode"] == "Markdown"


# ---------- send_document_html() ----------

def test_send_document_html_uses_html_parse_mode_for_caption(monkeypatch, tmp_path):
    """send_document_html with caption must use parse_mode=HTML."""
    from lib import notify
    f = tmp_path / "test.md"
    f.write_text("hello")
    captured = {}
    def fake_post(url, data=None, files=None, timeout=None):
        captured["data"] = data
        class R:
            def raise_for_status(self): pass
        return R()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(notify.requests, "post", fake_post)
    ok = notify.send_document_html(f, caption="<b>cap</b>")
    assert ok is True
    assert captured["data"]["parse_mode"] == "HTML"
    assert captured["data"]["caption"] == "<b>cap</b>"


def test_send_documents_html_returns_count(monkeypatch, tmp_path):
    """send_documents_html should mirror send_documents — first gets caption."""
    from lib import notify
    f1 = tmp_path / "a.md"; f1.write_text("a")
    f2 = tmp_path / "b.md"; f2.write_text("b")
    captures = []
    def fake_post(url, data=None, files=None, timeout=None):
        captures.append({"caption": data.get("caption") if data else None})
        class R:
            def raise_for_status(self): pass
        return R()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(notify.requests, "post", fake_post)
    n = notify.send_documents_html([f1, f2], caption="<b>first</b>")
    assert n == 2
    assert captures[0]["caption"] == "<b>first</b>"
    assert "caption" not in captures[1] or captures[1]["caption"] is None


# ---------------------------------------------------------------------------
# send_heartbeat() — no-op routine pings
# ---------------------------------------------------------------------------

def test_send_heartbeat_returns_false_without_credentials(no_creds):
    assert notify.send_heartbeat(
        routine="market_open",
        timestamp_utc="2026-05-15T13:35:00Z",
        mode="PAPER_TRADING",
        open_positions=0,
    ) is False


def test_send_heartbeat_posts_html_with_routine_and_state(stub_creds, monkeypatch):
    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    ok = notify.send_heartbeat(
        routine="market_open",
        timestamp_utc="2026-05-15T13:35:00Z",
        mode="PAPER_TRADING",
        open_positions=0,
        cb_state="FULL",
        equity_usd=102_496.62,
        exit_reason="noop",
    )
    assert ok is True
    text = captured["json"]["text"]
    assert "market_open" in text
    assert captured["json"]["parse_mode"] == "HTML"
    # The "no action" tag is the disambiguator vs a real action-summary message.
    assert "no action" in text
    assert "FULL" in text
    assert "102,496.62" in text
    assert "PAPER_TRADING" in text


def test_send_heartbeat_includes_extra_lines(stub_creds, monkeypatch):
    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.send_heartbeat(
        routine="midday",
        timestamp_utc="2026-05-15T16:03:00Z",
        mode="PAPER_TRADING",
        open_positions=0,
        cb_state="FULL",
        extra_lines=["<b>News:</b> connector REACHABLE"],
    )
    assert "News" in captured["json"]["text"]
    assert "REACHABLE" in captured["json"]["text"]


def test_send_heartbeat_omits_equity_when_none(stub_creds, monkeypatch):
    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.send_heartbeat(
        routine="midday",
        timestamp_utc="2026-05-15T16:03:00Z",
        mode="PAPER_TRADING",
        open_positions=0,
    )
    assert "Equity" not in captured["json"]["text"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
