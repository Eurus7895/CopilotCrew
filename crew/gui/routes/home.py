"""GET / — full-page shell with the morning view."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from crew.gui.routes._shared import get_config, get_templates
from crew.gui.services import mocks, pinned, standup_service, status_service

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    cfg = get_config(request)
    templates = get_templates(request)

    timeline = mocks.load_timeline(cfg)
    selected = timeline[0] if timeline else None

    ctx = {
        "cfg": cfg,
        "pinned_items": pinned.assemble(),
        "status": status_service.probe(cfg),
        "timeline": timeline,
        "selected_event": selected,
        "working_on": mocks.load_working_on(cfg),
        "facts": mocks.load_facts(cfg),
        "prs": mocks.load_pr_activity(cfg),
        "mentions": mocks.load_slack_mentions(cfg),
        "draft": standup_service.latest_draft(cfg),
    }
    return templates.TemplateResponse(request, "base.html", ctx)
