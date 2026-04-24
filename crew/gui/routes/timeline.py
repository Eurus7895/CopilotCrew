"""GET /timeline/{event_id} — swap center + right rail for a timeline event."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from crew.gui.routes._shared import (
    get_config,
    get_templates,
    is_htmx,
    resolve_theme,
    theme_context,
)
from crew.gui.services import mocks, pinned, standup_service, status_service

router = APIRouter(prefix="/timeline")


@router.get("/{event_id}", response_class=HTMLResponse)
async def timeline_event(request: Request, event_id: str) -> HTMLResponse:
    cfg = get_config(request)
    templates = get_templates(request)
    theme = resolve_theme(request)

    event = mocks.load_timeline_event(cfg, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"unknown timeline event: {event_id}")

    timeline = mocks.load_timeline(cfg)
    ctx = {
        "cfg": cfg,
        "pinned_items": pinned.assemble(),
        "status": status_service.probe(cfg),
        "timeline": timeline,
        "selected_event": event,
        "working_on": mocks.load_working_on(cfg),
        "facts": mocks.load_facts(cfg),
        "prs": mocks.load_pr_activity(cfg),
        "mentions": mocks.load_slack_mentions(cfg),
        "draft": standup_service.latest_draft(cfg),
        **theme_context(theme),
    }
    if is_htmx(request):
        template = f"themes/{theme}/center_timeline.html"
    else:
        template = "base.html"
    return templates.TemplateResponse(request, template, ctx)
