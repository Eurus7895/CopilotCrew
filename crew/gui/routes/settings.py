"""GET /settings — themed settings panel (inside the window).

POST /settings/theme/{name} — theme picker action: set the cookie and
redirect back to ``/settings``. The picker is the only user-facing way
to change the theme. The ``?theme=`` query param on ``/`` still works
but is developer-only.

The theme name lives in the URL path (not a form body) so the route
does not depend on python-multipart.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from crew.gui.routes._shared import (
    THEMES,
    THEME_COOKIE,
    get_config,
    get_templates,
    resolve_theme,
    theme_context,
)
from crew.gui.services import mocks, pinned, status_service

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request) -> HTMLResponse:
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
        "draft": None,
        "selected_page": "settings",
        **theme_context(theme),
    }
    return templates.TemplateResponse(request, "base.html", ctx)


@router.post("/settings/theme/{name}")
async def set_theme(request: Request, name: str) -> RedirectResponse:
    target = name.strip().lower()
    if target not in THEMES:
        target = resolve_theme(request)
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie(
        THEME_COOKIE,
        target,
        max_age=60 * 60 * 24 * 365,
        samesite="lax",
        httponly=False,
    )
    return response
