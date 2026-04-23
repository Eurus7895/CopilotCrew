"""Shared helpers for route modules."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from crew.gui.config import GUIConfig

_templates_cache: dict[str, Jinja2Templates] = {}


def get_templates(request: Request) -> Jinja2Templates:
    templates_dir: Path = request.app.state.templates_dir
    key = str(templates_dir)
    if key not in _templates_cache:
        _templates_cache[key] = Jinja2Templates(directory=str(templates_dir))
    return _templates_cache[key]


def get_config(request: Request) -> GUIConfig:
    return request.app.state.cfg


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"
