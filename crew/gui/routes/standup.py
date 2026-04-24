"""Standup draft card + regenerate/edit/skip actions (theme-aware)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from crew.gui.routes._shared import get_config, get_templates, resolve_theme
from crew.gui.services import editor, standup_service

router = APIRouter(prefix="/standup")


def _card_template(theme: str) -> str:
    return f"themes/{theme}/card_standup.html"


@router.get("/draft", response_class=HTMLResponse)
async def draft(request: Request) -> HTMLResponse:
    cfg = get_config(request)
    templates = get_templates(request)
    theme = resolve_theme(request)
    draft = standup_service.latest_draft(cfg)
    return templates.TemplateResponse(
        request, _card_template(theme), {"draft": draft, "theme": theme}
    )


@router.post("/run", response_class=Response)
async def run(request: Request) -> Response:
    cfg = get_config(request)
    if standup_service.is_running():
        raise HTTPException(status_code=409, detail="standup pipeline already running")
    asyncio.create_task(standup_service.run_generate(cfg))
    return Response(status_code=202, headers={"HX-Trigger": "standup-started"})


@router.post("/edit", response_class=Response)
async def edit(request: Request) -> Response:
    cfg = get_config(request)
    draft = standup_service.latest_draft(cfg)
    if draft.path is None:
        raise HTTPException(status_code=404, detail="no draft to edit")
    editor.open_in_editor(draft.path)
    return Response(status_code=204)


@router.post("/skip", response_class=HTMLResponse)
async def skip(request: Request) -> HTMLResponse:
    cfg = get_config(request)
    templates = get_templates(request)
    theme = resolve_theme(request)
    standup_service.delete_latest(cfg)
    draft = standup_service.latest_draft(cfg)
    return templates.TemplateResponse(
        request, _card_template(theme), {"draft": draft, "theme": theme}
    )
