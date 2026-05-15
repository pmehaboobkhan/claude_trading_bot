"""Tests for scripts/news_probe.py.

Exercises the probe verdict logic, the status-file format, and the CLI exit
codes. Network is mocked at the urllib level.
"""
from __future__ import annotations

import importlib.util
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBE_PATH = REPO_ROOT / "scripts" / "news_probe.py"


def _load_news_probe():
    """Load scripts/news_probe.py as a module (it has no `__init__.py`)."""
    spec = importlib.util.spec_from_file_location("news_probe", PROBE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["news_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def np():
    return _load_news_probe()


def test_probe_returns_reachable_on_200(np):
    class FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
    with patch.object(np.urllib.request, "urlopen", return_value=FakeResp()):
        reachable, detail = np.probe("https://example.com/")
    assert reachable is True
    assert "HTTP 200" in detail


def test_probe_returns_reachable_on_405_head_rejected(np):
    """SEC + many news endpoints reject HEAD with 405 — DNS+TCP+TLS still worked."""
    err = urllib.error.HTTPError(url="https://example.com/", code=405,
                                  msg="Method Not Allowed", hdrs=None, fp=None)
    with patch.object(np.urllib.request, "urlopen", side_effect=err):
        reachable, detail = np.probe("https://example.com/")
    assert reachable is True
    assert "405" in detail


def test_probe_returns_unreachable_on_503(np):
    err = urllib.error.HTTPError(url="https://example.com/", code=503,
                                  msg="Service Unavailable", hdrs=None, fp=None)
    with patch.object(np.urllib.request, "urlopen", side_effect=err):
        reachable, detail = np.probe("https://example.com/")
    assert reachable is False
    assert "503" in detail


def test_probe_returns_unreachable_on_dns_failure(np):
    err = urllib.error.URLError("Name or service not known")
    with patch.object(np.urllib.request, "urlopen", side_effect=err):
        reachable, detail = np.probe("https://example.com/")
    assert reachable is False
    assert "network error" in detail


def test_probe_returns_unreachable_on_timeout(np):
    with patch.object(np.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
        reachable, detail = np.probe("https://example.com/")
    assert reachable is False
    assert "network error" in detail


def test_write_status_emits_required_fields(np, tmp_path):
    path = np.write_status(
        reachable=True,
        detail="HTTP 200 from https://example.com/",
        url="https://example.com/",
        out_dir=tmp_path,
    )
    assert path == tmp_path / "_status.md"
    text = path.read_text(encoding="utf-8")
    assert "REACHABLE" in text
    assert "https://example.com/" in text
    assert "Probed (UTC):" in text


def test_write_status_unreachable_verdict(np, tmp_path):
    path = np.write_status(
        reachable=False,
        detail="network error",
        url="https://example.com/",
        out_dir=tmp_path,
    )
    text = path.read_text(encoding="utf-8")
    assert "UNREACHABLE" in text


def test_main_exits_zero_when_reachable(np, tmp_path, capsys):
    class FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
    with patch.object(np.urllib.request, "urlopen", return_value=FakeResp()):
        code = np.main(["--out-dir", str(tmp_path), "--quiet"])
    assert code == 0
    assert (tmp_path / "_status.md").exists()


def test_main_exits_one_when_unreachable(np, tmp_path):
    err = urllib.error.URLError("down")
    with patch.object(np.urllib.request, "urlopen", side_effect=err):
        code = np.main(["--out-dir", str(tmp_path), "--quiet"])
    assert code == 1
    assert "UNREACHABLE" in (tmp_path / "_status.md").read_text(encoding="utf-8")
