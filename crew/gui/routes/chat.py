"""POST /chat — user types a message, assistant reply streams over SSE.

The POST is the "echo" endpoint: it records the user message + an
assistant-bubble placeholder id, renders a theme-appropriate HTML
fragment that HTMX appends to the chat list, and spawns a background
task that fills in the assistant bubble via ``chat_token`` SSE events.

JS (app.js) listens for ``chat_token`` events and appends deltas into
the ``#chat-msg-<id>`` node the fragment dropped in; ``chat_done``
finalises the bubble; ``chat_error`` swaps in an error strip.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from crew.gui.routes._shared import get_config, get_templates, resolve_theme
from crew.gui.services import chat_service

router = APIRouter()


@router.post("/chat", response_class=HTMLResponse)
async def chat(request: Request, message: str = Form(...)) -> HTMLResponse:
    text = message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty message")

    cfg = get_config(request)
    templates = get_templates(request)
    theme = resolve_theme(request)

    echo = await chat_service.send_message(cfg, text)
    return templates.TemplateResponse(
        request,
        f"themes/{theme}/chat_turn.html",
        {
            "message_id": echo.message_id,
            "user_text": echo.user_text,
            "theme": theme,
        },
    )
