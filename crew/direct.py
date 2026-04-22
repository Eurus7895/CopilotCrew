"""Direct mode — single Copilot SDK call, streamed to stdout.

Per CLAUDE.md "Execution Modes / Direct Mode": no pipeline, no governance,
just answer. MCP is available so the user can ask data-lookup questions
("how many open PRs?") without invoking a pipeline.

A standalone agent (``agents/<name>.md``) can be layered on top: pass
``agent_prompt=...`` to swap the system prompt for a persona like
``coder`` without otherwise changing direct-mode behaviour. No plan JSON,
no output file — persona swap only.
"""

from __future__ import annotations

import sys
from typing import Any

from copilot import CopilotClient
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.session import PermissionHandler

DIRECT_SYSTEM_PROMPT = "You are a helpful team assistant."


async def run_direct(
    user_input: str,
    *,
    model: str | None = None,
    agent_prompt: str | None = None,
) -> None:
    """Send `user_input` as a one-shot prompt and stream the reply to stdout.

    When ``agent_prompt`` is supplied, it replaces the SDK's default system
    message for this call (persona swap). MCP discovery stays enabled so
    agents that need GitHub or other MCP tools can still reach them.
    """

    def on_event(event: SessionEvent) -> None:
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                sys.stdout.write(delta)
                sys.stdout.flush()

    session_kwargs: dict[str, Any] = {
        "on_permission_request": PermissionHandler.approve_all,
        "model": model,
        "streaming": True,
        "enable_config_discovery": True,
    }
    if agent_prompt:
        session_kwargs["system_message"] = {
            "mode": "replace",
            "content": agent_prompt.strip(),
        }

    async with CopilotClient() as client:
        async with await client.create_session(**session_kwargs) as session:
            session.on(on_event)
            await session.send_and_wait(user_input)
            sys.stdout.write("\n")
            sys.stdout.flush()
