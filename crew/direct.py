"""Direct mode — single Copilot SDK call, streamed to stdout.

Per CLAUDE.md "Execution Modes / Direct Mode": no pipeline, no governance,
just answer. MCP is available so the user can ask data-lookup questions
("how many open PRs?") without invoking a pipeline.

Two optional layers can be composed on top:

* ``agent_prompt`` — swap the system prompt for a persona (``agents/*.md``).
  Implemented via ``system_message={"mode": "replace", ...}``.
* ``skill_prompt`` — append a skill's instructions as additional system
  content (``skills/<name>/SKILL.md``). When combined with ``agent_prompt``,
  they concatenate into a single ``replace`` message. When used alone,
  the skill appends to the SDK's CLI foundation via ``append`` mode.

No plan JSON, no output file — direct mode stays lightweight.
"""

from __future__ import annotations

import sys
from typing import Any

from copilot import CopilotClient
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.session import PermissionHandler

DIRECT_SYSTEM_PROMPT = "You are a helpful team assistant."


def _build_system_message(
    agent_prompt: str | None,
    skill_prompt: str | None,
) -> dict[str, Any] | None:
    """Return the ``system_message`` kwarg for ``create_session``, or None.

    - agent only      → replace with agent prompt
    - agent + skill   → replace with ``agent + "\\n\\n" + skill``
    - skill only      → append skill to SDK's CLI foundation
    - neither         → None (SDK uses its default prompt)
    """
    agent = (agent_prompt or "").strip()
    skill = (skill_prompt or "").strip()
    if agent and skill:
        return {"mode": "replace", "content": f"{agent}\n\n{skill}"}
    if agent:
        return {"mode": "replace", "content": agent}
    if skill:
        return {"mode": "append", "content": skill}
    return None


async def run_direct(
    user_input: str,
    *,
    model: str | None = None,
    agent_prompt: str | None = None,
    skill_prompt: str | None = None,
) -> None:
    """Send `user_input` as a one-shot prompt and stream the reply to stdout.

    ``agent_prompt`` swaps the system message for a persona. ``skill_prompt``
    appends a skill's instructions as additional system content. Both
    default to the SDK's built-in prompt behaviour.
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
    system_message = _build_system_message(agent_prompt, skill_prompt)
    if system_message is not None:
        session_kwargs["system_message"] = system_message

    async with CopilotClient() as client:
        async with await client.create_session(**session_kwargs) as session:
            session.on(on_event)
            await session.send_and_wait(user_input)
            sys.stdout.write("\n")
            sys.stdout.flush()
