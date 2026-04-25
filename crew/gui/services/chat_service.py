"""Chat bridge: user-typed messages → ``crew.direct.run_direct`` → SSE.

Each message spawns a background task that calls run_direct with a
:class:`CallbackStreamer` publishing ``chat_token`` events onto the
in-process events bus. The browser listens via ``/events/stream`` and
appends tokens into the active assistant bubble in real time.

Per-scope session continuity reuses ``crew/conversations.py`` so the GUI
chat honours ``CREW_TURN_CAP`` rotation identically to the CLI's direct
mode. Pipelines and the evaluator still never resume (CLAUDE.md
principle #2) — chat is direct mode only.

The Copilot SDK is imported lazily inside ``send_message`` so the GUI
package still boots without it (read-only viewers don't need chat).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from crew.gui.config import GUIConfig
from crew.gui.services.events_bus import publish

_log = logging.getLogger("crew.gui.chat_service")


@dataclass(frozen=True)
class ChatEchoed:
    """Returned to the caller synchronously — the user message + the
    placeholder id that the streamed assistant reply will target."""
    message_id: str
    user_text: str


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


async def send_message(cfg: GUIConfig, user_text: str) -> ChatEchoed:
    """Echo the user message immediately; stream the assistant reply.

    Returns quickly with the message id + user text so the route handler
    can render them into the chat list. The actual LLM call runs on a
    background task — tokens arrive via SSE as ``chat_token`` events.
    """
    message_id = _new_id()
    echo = ChatEchoed(message_id=message_id, user_text=user_text)

    async def _drive():
        try:
            from crew import conversations
            from crew.direct import run_direct
            from crew.streamer import CallbackStreamer
        except ImportError as exc:
            await publish(
                "chat_error",
                {
                    "message_id": message_id,
                    "detail": f"copilot SDK not installed: {exc}",
                },
            )
            return

        # Scope is the same as the CLI's direct-mode scope: (cwd, mode, None).
        scope = conversations.compute_scope(cwd=Path(cfg.crew_home), mode="direct", agent=None)
        state = conversations.load_session(scope)

        history_prompt: str | None = None
        session_id: str | None = None
        next_turn_count = 1
        started_at: str | None = None
        if state is not None:
            if conversations.should_rotate(state):
                history_prompt = await conversations.summarize_for_rotation(scope, model=cfg.model)
                conversations.append_event(
                    scope,
                    "rotated",
                    {
                        "old_session_id": state.session_id,
                        "old_turn_count": state.turn_count,
                        "summary": history_prompt,
                    },
                )
                session_id = None
                next_turn_count = 1
                started_at = state.started_at
            else:
                session_id = state.session_id
                next_turn_count = state.turn_count + 1
                started_at = state.started_at

        loop = asyncio.get_event_loop()

        def on_delta(text: str) -> None:
            coro = publish("chat_token", {"message_id": message_id, "delta": text})
            try:
                asyncio.ensure_future(coro, loop=loop)
            except RuntimeError:
                pass  # loop closed — drop

        streamer = CallbackStreamer(on_delta_fn=on_delta)
        try:
            result = await run_direct(
                user_text,
                model=cfg.model,
                history_prompt=history_prompt,
                session_id=session_id,
                streamer=streamer,
            )
        except Exception as exc:
            _log.exception("chat direct call failed")
            await publish(
                "chat_error",
                {"message_id": message_id, "detail": str(exc)},
            )
            return

        conversations.append_turn(
            scope,
            mode="direct",
            agent=None,
            user=user_text,
            assistant=result.assistant_text,
            session_id=result.session_id,
        )
        conversations.save_session(
            scope,
            session_id=result.session_id,
            turn_count=next_turn_count,
            cwd=Path(cfg.crew_home),
            mode="direct",
            agent=None,
            started_at=started_at,
        )
        await publish(
            "chat_done",
            {"message_id": message_id, "text": result.assistant_text},
        )

    asyncio.create_task(_drive())
    return echo
