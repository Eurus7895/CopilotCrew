"""POST /pinned/{kind}/{name} — click handlers for left-rail pinned items.

Kinds: ``skill`` / ``agent`` / ``pipeline`` / ``memory``. Each dispatches
to crew core primitives via crew.gui.services.pinned_actions and returns
a theme-appropriate "an assistant reply is streaming" fragment that
HTMX appends to the chat list — identical UX to typing into the chat
composer.

The special ``memory`` kind opens ``~/.crew/memory.jsonl`` in ``$EDITOR``
and returns 204.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from crew.gui.routes._shared import get_config, get_templates, resolve_theme
from crew.gui.services import pinned_actions

router = APIRouter(prefix="/pinned")


async def _render_turn(request, *, theme, message_id, user_text):
    templates = get_templates(request)
    return templates.TemplateResponse(
        request,
        f"themes/{theme}/chat_turn.html",
        {"message_id": message_id, "user_text": user_text, "theme": theme},
    )


@router.post("/skill/{name}", response_class=HTMLResponse)
async def invoke_skill(
    request: Request, name: str, message: str = Form(default="")
) -> HTMLResponse:
    cfg = get_config(request)
    theme = resolve_theme(request)
    text = message.strip() or f"What does the /{name} skill do? Help me use it."
    message_id = await pinned_actions.invoke_skill(cfg, name, text)
    return await _render_turn(request, theme=theme, message_id=message_id, user_text=f"/{name} {text}".strip())


@router.post("/agent/{name}", response_class=HTMLResponse)
async def invoke_agent(
    request: Request, name: str, message: str = Form(default="")
) -> HTMLResponse:
    cfg = get_config(request)
    theme = resolve_theme(request)
    text = message.strip() or f"Hi @{name} — what do you want to work on?"
    message_id = await pinned_actions.invoke_agent(cfg, name, text)
    return await _render_turn(request, theme=theme, message_id=message_id, user_text=f"@{name} — {text}")


@router.post("/pipeline/{name}", response_class=HTMLResponse)
async def invoke_pipeline(
    request: Request, name: str, message: str = Form(default="")
) -> HTMLResponse:
    cfg = get_config(request)
    theme = resolve_theme(request)
    text = message.strip() or ""
    message_id = await pinned_actions.invoke_pipeline(cfg, name, text)
    label = f"/{name}"
    if text:
        label = f"{label} — {text}"
    return await _render_turn(request, theme=theme, message_id=message_id, user_text=label)


@router.post("/memory", response_class=Response)
async def open_memory(request: Request) -> Response:
    cfg = get_config(request)
    ok = pinned_actions.open_memory(cfg)
    if not ok:
        raise HTTPException(status_code=400, detail="no $EDITOR configured")
    return Response(status_code=204)
