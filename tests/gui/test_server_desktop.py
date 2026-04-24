"""PyWebView desktop-window wrapping + --no-window fallback.

These tests exercise crew.gui.server.run_server directly, mocking
pywebview and uvicorn so nothing actually listens or opens a window.
"""

from __future__ import annotations

import sys
import types

import pytest

from crew.gui import server as server_mod


class _FakeUvicornServer:
    def __init__(self, config):
        self.config = config
        self.ran = False
        self.should_exit = False

    def run(self):
        self.ran = True


class _FakeWebview:
    def __init__(self):
        self.windows: list[tuple[str, str, dict]] = []
        self.started = False

    def create_window(self, title, url, **kwargs):
        self.windows.append((title, url, kwargs))

    def start(self, *a, **kw):
        self.started = True


@pytest.fixture
def fake_uvicorn(monkeypatch):
    instances: list[_FakeUvicornServer] = []

    def _Server(config):
        s = _FakeUvicornServer(config)
        instances.append(s)
        return s

    monkeypatch.setattr(server_mod.uvicorn, "Config", lambda *a, **kw: dict(a=a, kw=kw))
    monkeypatch.setattr(server_mod.uvicorn, "Server", _Server)
    return instances


@pytest.fixture
def fake_webview(monkeypatch):
    fake = _FakeWebview()
    mod = types.ModuleType("webview")
    mod.create_window = fake.create_window
    mod.start = fake.start
    monkeypatch.setitem(sys.modules, "webview", mod)
    return fake


@pytest.fixture
def skip_uvicorn_ready(monkeypatch):
    monkeypatch.setattr(server_mod, "_wait_ready", lambda *a, **kw: None)


def test_run_server_opens_native_window(monkeypatch, tmp_path, fake_uvicorn, fake_webview, skip_uvicorn_ready):
    # Fake the thread so uvicorn doesn't actually run.
    starts: list = []

    class _FakeThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            starts.append(self.target)

    monkeypatch.setattr(server_mod.threading, "Thread", _FakeThread)
    monkeypatch.setattr(server_mod, "_find_free_port", lambda _host: 54321)
    monkeypatch.setenv("CREW_HOME", str(tmp_path))

    server_mod.run_server(open_window=True, model="gpt-4.1")

    assert fake_webview.started is True
    assert len(fake_webview.windows) == 1
    title, url, kwargs = fake_webview.windows[0]
    assert title.startswith("Crew — ")
    assert url == "http://127.0.0.1:54321/"
    assert kwargs["width"] >= 1024 and kwargs["height"] >= 600
    # uvicorn's .run was queued on a thread.
    assert len(starts) == 1


def test_run_server_falls_back_when_pywebview_missing(monkeypatch, tmp_path):
    """Import failure on ``webview`` drops us into server-only mode."""
    # Guarantee ``import webview`` fails.
    monkeypatch.setitem(sys.modules, "webview", None)

    called: dict[str, object] = {}

    def fake_blocking(app, host, port, *, open_browser):
        called["args"] = (host, port, open_browser)

    monkeypatch.setattr(server_mod, "_run_blocking", fake_blocking)
    monkeypatch.setattr(server_mod, "_find_free_port", lambda _host: 12345)
    monkeypatch.setenv("CREW_HOME", str(tmp_path))

    server_mod.run_server(open_window=True)

    # Blocking fallback was invoked with open_browser=True so the user can still reach it.
    assert called["args"] == ("127.0.0.1", 12345, True)


def test_run_server_no_window_uses_fixed_port(monkeypatch, tmp_path):
    called: dict[str, object] = {}

    def fake_blocking(app, host, port, *, open_browser):
        called["args"] = (host, port, open_browser)

    monkeypatch.setattr(server_mod, "_run_blocking", fake_blocking)
    monkeypatch.setenv("CREW_HOME", str(tmp_path))

    server_mod.run_server(open_window=False, port=None, open_browser=True)

    # With --no-window and no --port, we default to 8765 (stable URL for bookmarks/dev).
    assert called["args"] == ("127.0.0.1", 8765, True)
