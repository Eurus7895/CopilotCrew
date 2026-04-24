"""Shared helpers for route modules."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from crew.gui.config import GUIConfig

_templates_cache: dict[str, Jinja2Templates] = {}

THEMES = ("warm", "terminal", "modernist")
DEFAULT_THEME = "warm"
THEME_COOKIE = "crew_theme"

THEME_META = {
    "warm": {
        "tab_label": "Warm · Workspace",
        "tag": "warm",
        "tagline": "Warm neutrals, paper cards with soft shadow, a polaroid avatar. Crew as a coworker you'd actually want at your desk.",
    },
    "terminal": {
        "tab_label": "Terminal · Operator",
        "tag": "terminal",
        "tagline": "tmux-style operator console. Phosphor amber on pitch black, ASCII section rules, vim keybindings, CRT scanlines.",
    },
    "modernist": {
        "tab_label": "Modernist · Swiss",
        "tag": "modernist",
        "tagline": "12-col grid, Archivo, signal-red accent. Giant numerals, all-caps mono labels. Bloomberg energy with editorial restraint.",
    },
}


def _loop_index_for(rows: list[dict] | None, target_id: str | None) -> int:
    """1-based index of the row whose ``id`` matches ``target_id``, else 1."""
    if not rows or not target_id:
        return 1
    for idx, row in enumerate(rows, start=1):
        if str(row.get("id")) == target_id:
            return idx
    return 1


_MOD_OBS_LABELS = (
    "Priya · stance",
    "Alex-p · context",
    "Flake · signature",
    "Day 3 · estimate",
    "Observation",
)


def _mod_obs_label(idx: int, fact: dict) -> str:
    """Swiss-theme observation header: fixed rotation, upper-cased."""
    if "label" in fact and isinstance(fact["label"], str) and fact["label"]:
        return fact["label"].upper()
    try:
        return _MOD_OBS_LABELS[idx].upper()
    except (IndexError, TypeError):
        return _MOD_OBS_LABELS[-1].upper()


def get_templates(request: Request) -> Jinja2Templates:
    templates_dir: Path = request.app.state.templates_dir
    key = str(templates_dir)
    if key not in _templates_cache:
        env = Jinja2Templates(directory=str(templates_dir))
        env.env.globals["loop_index_for"] = _loop_index_for
        env.env.filters["mod_obs_label"] = _mod_obs_label
        _templates_cache[key] = env
    return _templates_cache[key]


def get_config(request: Request) -> GUIConfig:
    return request.app.state.cfg


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


def resolve_theme(request: Request) -> str:
    """Pick the active theme: query param wins, then cookie, else default."""
    q = (request.query_params.get("theme") or "").strip().lower()
    if q in THEMES:
        return q
    c = (request.cookies.get(THEME_COOKIE) or "").strip().lower()
    if c in THEMES:
        return c
    return DEFAULT_THEME


def theme_context(theme: str) -> dict:
    """Common template context for rendering any theme."""
    return {
        "theme": theme,
        "themes": THEMES,
        "theme_meta": THEME_META,
    }
