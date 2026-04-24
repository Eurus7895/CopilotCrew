"""In-process pub/sub delivers events to subscribers."""

from __future__ import annotations

import asyncio

import pytest

from crew.gui.services import events_bus


@pytest.mark.asyncio
async def test_publish_reaches_subscriber():
    received: list[dict] = []

    async def consumer():
        async for payload in events_bus.subscribe():
            received.append(payload)
            if len(received) >= 1:
                break

    task = asyncio.create_task(consumer())
    # Give the consumer a chance to register the queue.
    await asyncio.sleep(0)
    await events_bus.publish("pipeline_progress", {"state": "delta", "delta": "hi"})
    await asyncio.wait_for(task, timeout=1.0)

    assert received == [{
        "event": "pipeline_progress",
        "data": {"state": "delta", "delta": "hi"},
    }]


@pytest.mark.asyncio
async def test_publish_without_subscribers_is_noop():
    # Just shouldn't raise.
    await events_bus.publish("pipeline_progress", {"state": "ok"})
