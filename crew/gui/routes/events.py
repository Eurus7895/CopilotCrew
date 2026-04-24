"""GET /events/stream — SSE fan-out of the in-process event bus."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from crew.gui.services import events_bus

router = APIRouter()


@router.get("/events/stream")
async def events_stream(request: Request) -> EventSourceResponse:
    async def generator():
        async for payload in events_bus.subscribe():
            if await request.is_disconnected():
                break
            yield {
                "event": payload["event"],
                "data": json.dumps(payload["data"]),
            }

    return EventSourceResponse(generator())
