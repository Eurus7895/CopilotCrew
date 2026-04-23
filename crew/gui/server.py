"""Uvicorn wrapper for ``crew gui``."""

from __future__ import annotations

import asyncio
import threading
import time
import webbrowser

import uvicorn

from crew.gui.app import create_app
from crew.gui.config import GUIConfig


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    model: str | None = None,
) -> None:
    cfg = GUIConfig.build(model=model, host=host, port=port)
    app = create_app(cfg)

    if open_browser:
        threading.Thread(
            target=_open_browser_later,
            args=(f"http://{host}:{port}/",),
            daemon=True,
        ).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        pass


def _open_browser_later(url: str) -> None:
    time.sleep(0.3)
    try:
        webbrowser.open(url)
    except Exception:
        pass
