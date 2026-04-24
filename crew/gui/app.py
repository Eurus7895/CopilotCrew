"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from crew.gui.config import GUIConfig
from crew.gui.services import bootstrap

_HERE = Path(__file__).parent
_STATIC_DIR = _HERE / "static"
_TEMPLATES_DIR = _HERE / "templates"
_FIXTURES_DIR = _HERE / "fixtures" / "seed"


def create_app(config: GUIConfig | None = None) -> FastAPI:
    cfg = config or GUIConfig.build()
    bootstrap.seed_gui_dir(cfg.gui_dir, _FIXTURES_DIR)
    bootstrap.seed_memory(cfg.memory_path, _FIXTURES_DIR / "memory.jsonl")
    # Ensure outputs directory exists so file-watch SSE can attach.
    (cfg.outputs_dir / "daily-standup").mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Crew", docs_url=None, redoc_url=None)
    app.state.cfg = cfg
    app.state.templates_dir = _TEMPLATES_DIR
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:  # noqa: D401 - simple probe
        return JSONResponse({"ok": True})

    # Lazy imports so route modules can freely import app.state shape.
    from crew.gui.routes import context, events, home, settings, standup, status, timeline

    app.include_router(home.router)
    app.include_router(timeline.router)
    app.include_router(context.router)
    app.include_router(standup.router)
    app.include_router(status.router)
    app.include_router(events.router)
    app.include_router(settings.router)

    return app
