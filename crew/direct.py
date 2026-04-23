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
* ``history_prompt`` — append a one-paragraph handoff summary (produced
  by ``crew/conversations.summarize_for_rotation``) so a freshly-rotated
  session sees the gist of what came before. Composes with the others —
  always concatenated as the LAST chunk so it sits closest to the user
  message.

``session_id`` is the Copilot SDK's session-resumption hook. When passed,
Copilot replays the prior turns of that session server-side; when None,
a fresh session is created. Direct mode returns the resolved session_id
+ the assistant's text so the caller can persist them to
``~/.crew/conversations`` (per the harness principle that structured
artifacts must survive context resets).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from copilot import CopilotClient
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.session import PermissionHandler

DIRECT_SYSTEM_PROMPT = "You are a helpful team assistant."


@dataclass(frozen=True)
class DirectResult:
    session_id: str
    assistant_text: str


def _build_system_message(
    agent_prompt: str | None,
    skill_prompt: str | None,
    history_prompt: str | None = None,
) -> dict[str, Any] | None:
    """Return the ``system_message`` kwarg for ``create_session``, or None.

    History (when present) is concatenated last so it sits nearest the
    user message — same ordering as Claude Code's compaction handoff.

    - agent only          → replace with agent prompt
    - agent + skill       → replace with ``agent + "\\n\\n" + skill``
    - skill only          → append skill to SDK's CLI foundation
    - + history (any)     → suffix the chosen content with the history
                             paragraph; mode stays whatever it would
                             otherwise be
    - none of the above   → None (SDK uses its default prompt)
    """
    agent = (agent_prompt or "").strip()
    skill = (skill_prompt or "").strip()
    history = (history_prompt or "").strip()
    history_block = f"\n\n## Previous conversation summary\n\n{history}" if history else ""

    if agent and skill:
        return {"mode": "replace", "content": f"{agent}\n\n{skill}{history_block}"}
    if agent:
        return {"mode": "replace", "content": f"{agent}{history_block}"}
    if skill:
        return {"mode": "append", "content": f"{skill}{history_block}"}
    if history:
        return {"mode": "append", "content": history_block.lstrip("\n")}
    return None


async def run_direct(
    user_input: str,
    *,
    model: str | None = None,
    agent_prompt: str | None = None,
    skill_prompt: str | None = None,
    history_prompt: str | None = None,
    session_id: str | None = None,
) -> DirectResult:
    """Send `user_input` and stream the reply to stdout.

    Returns a ``DirectResult(session_id, assistant_text)`` so the caller
    can persist the conversation. ``session_id`` (in) resumes an existing
    Copilot session; ``DirectResult.session_id`` (out) is what to remember
    for the next turn (it may differ if the SDK assigned a new id).
    """
    buffer: list[str] = []

    def on_event(event: SessionEvent) -> None:
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                sys.stdout.write(delta)
                sys.stdout.flush()
                buffer.append(delta)

    session_kwargs: dict[str, Any] = {
        "on_permission_request": PermissionHandler.approve_all,
        "model": model,
        "streaming": True,
        "enable_config_discovery": True,
    }
    if session_id is not None:
        session_kwargs["session_id"] = session_id
    system_message = _build_system_message(agent_prompt, skill_prompt, history_prompt)
    if system_message is not None:
        session_kwargs["system_message"] = system_message

    async with CopilotClient() as client:
        async with await client.create_session(**session_kwargs) as session:
            session.on(on_event)
            await session.send_and_wait(user_input)
            sys.stdout.write("\n")
            sys.stdout.flush()
            resolved_session_id = getattr(session, "session_id", None) or session_id or ""

    return DirectResult(
        session_id=resolved_session_id,
        assistant_text="".join(buffer).strip(),
    )
