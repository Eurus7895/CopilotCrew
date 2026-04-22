"""Direct mode — single Copilot SDK call, streamed to stdout.

Per CLAUDE.md "Execution Modes / Direct Mode": no pipeline, no governance,
just answer. MCP is available so the user can ask data-lookup questions
("how many open PRs?") without invoking a pipeline.
"""

from __future__ import annotations

import sys

from copilot import CopilotClient
from copilot.generated.session_events import (
    AssistantMessageDeltaData,
    SessionEvent,
)
from copilot.session import PermissionHandler

DIRECT_SYSTEM_PROMPT = "You are a helpful team assistant."


async def run_direct(user_input: str, *, model: str | None = None) -> None:
    """Send `user_input` as a one-shot prompt and stream the reply to stdout."""

    def on_event(event: SessionEvent) -> None:
        match event.data:
            case AssistantMessageDeltaData() as data:
                sys.stdout.write(data.delta_content or "")
                sys.stdout.flush()

    async with CopilotClient() as client:
        async with await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=model,
            streaming=True,
            enable_config_discovery=True,
        ) as session:
            session.on(on_event)
            await session.send_and_wait(user_input)
            sys.stdout.write("\n")
            sys.stdout.flush()
