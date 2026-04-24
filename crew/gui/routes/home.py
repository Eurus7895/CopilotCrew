"""GET / — full-page shell with the morning view, theme-aware."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from crew.gui.routes._shared import (
    THEME_COOKIE,
    get_config,
    get_templates,
    resolve_theme,
    theme_context,
)
from crew.gui.services import mocks, pinned, standup_service, status_service

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    cfg = get_config(request)
    templates = get_templates(request)
    theme = resolve_theme(request)

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
        **theme_context(theme),
    }
    response = templates.TemplateResponse(request, "base.html", ctx)
    # Persist the theme choice when it came in via query param.
    if request.query_params.get("theme"):
        response.set_cookie(
            THEME_COOKIE,
            theme,
            max_age=60 * 60 * 24 * 365,
            samesite="lax",
            httponly=False,
        )
    return response
