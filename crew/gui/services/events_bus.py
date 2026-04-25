"""In-process pub/sub for SSE streaming.

Routes publish event dicts; ``/events/stream`` subscribes and fans them
out to connected browsers as ``text/event-stream``. The bus is process-
local — multi-process deployments would need a Redis backplane, which is
out of scope for v1 (GUI binds 127.0.0.1).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()


@dataclass(frozen=True)
class Event:
    name: str           # SSE event name (e.g. "pipeline_progress")
    data: dict[str, Any]


async def publish(name: str, data: dict[str, Any]) -> None:
    payload: dict[str, Any] = {"event": name, "data": data}
    for queue in list(_subscribers):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            continue


async def subscribe() -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
    _subscribers.add(queue)
    try:
        while True:
            item = await queue.get()
            yield item
    finally:
        _subscribers.discard(queue)


def subscriber_count() -> int:
    return len(_subscribers)
