"""GET /context — right-rail partial refresh."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from crew.gui.routes._shared import get_config, get_templates
from crew.gui.services import mocks

router = APIRouter()


@router.get("/context", response_class=HTMLResponse)
async def context(request: Request) -> HTMLResponse:
    cfg = get_config(request)
    templates = get_templates(request)
    timeline = mocks.load_timeline(cfg)
    ctx = {
        "cfg": cfg,
        "timeline": timeline,
        "selected_event": timeline[0] if timeline else None,
        "working_on": mocks.load_working_on(cfg),
        "facts": mocks.load_facts(cfg),
    }
    return templates.TemplateResponse(request, "partials/right_rail.html", ctx)
