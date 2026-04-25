"""GET /context — right-rail partial refresh (theme-aware)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from crew.gui.routes._shared import get_config, get_templates, resolve_theme, theme_context
from crew.gui.services import mocks, pinned, status_service

router = APIRouter()


@router.get("/context", response_class=HTMLResponse)
async def context(request: Request) -> HTMLResponse:
    cfg = get_config(request)
    templates = get_templates(request)
    theme = resolve_theme(request)
    timeline = mocks.load_timeline(cfg)
    ctx = {
        "cfg": cfg,
        "pinned_items": pinned.assemble(),
        "status": status_service.probe(cfg),
        "timeline": timeline,
        "selected_event": timeline[0] if timeline else None,
        "working_on": mocks.load_working_on(cfg),
        "facts": mocks.load_facts(cfg),
        "prs": mocks.load_pr_activity(cfg),
        "mentions": mocks.load_slack_mentions(cfg),
        **theme_context(theme),
    }
    return templates.TemplateResponse(request, f"themes/{theme}/right_rail.html", ctx)
