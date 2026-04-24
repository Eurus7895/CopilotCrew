"""``crew gui`` entrypoint — launches a native desktop window by default.

A FastAPI/uvicorn server runs on a localhost port inside a daemon
thread; the user-visible surface is a PyWebView window pointing at
that port. Users do not see the URL, do not open a browser, and do not
manage a server — the window *is* the app. The daemon server exits
with the process when the window closes.

Headless / CI fallback: ``--no-window`` skips PyWebView and keeps the
old "blocking uvicorn" behaviour, which is what the test suite uses and
what a remote-dev scenario needs.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

import uvicorn

from crew.gui.app import create_app
from crew.gui.config import GUIConfig

_log = logging.getLogger("crew.gui.server")


def _find_free_port(host: str) -> int:
    """Ask the kernel for an unused port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_window: bool = True,
    open_browser: bool = False,
    model: str | None = None,
    width: int = 1360,
    height: int = 900,
) -> None:
    """Launch the GUI. Opens a native window unless ``open_window=False``.

    :param host: server bind host (defaults to 127.0.0.1).
    :param port: server port; if ``None`` a free port is chosen automatically.
        With ``open_window=False``, a fixed default (8765) is used for
        stability of the "run as a local server" workflow.
    :param open_window: when True (default), start a PyWebView native
        window pointing at the server. When False, block on uvicorn and
        let the caller reach it via a browser.
    :param open_browser: when True and ``open_window`` is False, open
        the default system browser after the server is ready. Ignored
        when the native window is shown (it is the interaction surface).
    """
    resolved_port = port if port is not None else (_find_free_port(host) if open_window else 8765)
    cfg = GUIConfig.build(model=model, host=host, port=resolved_port)
    app = create_app(cfg)

    if not open_window:
        _run_blocking(app, host, resolved_port, open_browser=open_browser)
        return

    _run_with_window(
        app, host=host, port=resolved_port, title=f"Crew — {cfg.user_name}",
        width=width, height=height,
    )


# ── native window (default) ────────────────────────────────────────────


def _run_with_window(app, *, host: str, port: int, title: str, width: int, height: int) -> None:
    try:
        import webview  # pywebview
    except ImportError:
        _log.warning(
            "pywebview not installed — falling back to server-only mode. "
            "Install `pip install 'crew[gui]'` to get the desktop window."
        )
        _run_blocking(app, host, port, open_browser=True)
        return

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    # Uvicorn in a daemon thread so the native event loop can own the main thread.
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_ready(host, port)

    url = f"http://{host}:{port}/"
    webview.create_window(title, url=url, width=width, height=height, resizable=True)
    try:
        webview.start()  # blocks until the window is closed
    finally:
        # Ask uvicorn to stop; the daemon thread will exit on process tear-down.
        server.should_exit = True


# ── blocking server (CI / --no-window / remote dev) ────────────────────


def _run_blocking(app, host: str, port: int, *, open_browser: bool) -> None:
    import asyncio
    import webbrowser

    if open_browser:
        threading.Thread(
            target=_open_browser_later, args=(f"http://{host}:{port}/",), daemon=True
        ).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        pass


def _open_browser_later(url: str) -> None:
    import webbrowser
    time.sleep(0.3)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def _wait_ready(host: str, port: int, timeout: float = 5.0) -> None:
    """Block briefly until uvicorn is accepting connections on ``(host, port)``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.connect((host, port))
                return
            except OSError:
                time.sleep(0.05)
    _log.warning("uvicorn did not become ready within %.1fs", timeout)
