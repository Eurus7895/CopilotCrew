"""Dispatch a click on a pinned-item to the right Crew primitive.

Skills → append the skill to a direct-mode system message and run the
user's message against it. Agents → swap the system prompt for the
persona and run. Pipelines → kick off a run via the existing concurrency
lock pattern. The special ``memory.jsonl`` pinned entry opens the file
in ``$EDITOR``.

All of this reuses crew core primitives — this module is a routing
layer, not a reimplementation.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from crew.gui.config import GUIConfig
from crew.gui.services import editor, standup_service
from crew.gui.services.events_bus import publish

_log = logging.getLogger("crew.gui.pinned_actions")


class UnknownPinnedItem(Exception):
    pass


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


async def invoke_skill(cfg: GUIConfig, skill_name: str, user_text: str) -> str:
    """Run a direct-mode turn with ``skill_name`` appended to the system
    prompt. Returns a message id the caller can render; tokens stream
    via SSE ``chat_token`` events (same channel as /chat)."""
    message_id = _new_id()
    asyncio.create_task(_drive_skill(cfg, skill_name, user_text, message_id))
    return message_id


async def invoke_agent(cfg: GUIConfig, agent_name: str, user_text: str) -> str:
    """Run a direct-mode turn with the persona's system prompt."""
    message_id = _new_id()
    asyncio.create_task(_drive_agent(cfg, agent_name, user_text, message_id))
    return message_id


async def invoke_pipeline(cfg: GUIConfig, pipeline_name: str, user_text: str) -> str:
    """Kick off a pipeline run. Protected by the existing standup lock
    for the daily-standup pipeline; other pipelines share no lock since
    they're independent."""
    message_id = _new_id()
    asyncio.create_task(_drive_pipeline(cfg, pipeline_name, user_text, message_id))
    return message_id


def open_memory(cfg: GUIConfig) -> bool:
    """Open ``memory.jsonl`` in $EDITOR."""
    cfg.memory_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.memory_path.touch(exist_ok=True)
    return editor.open_in_editor(cfg.memory_path)


# ── drivers ─────────────────────────────────────────────────────────


async def _drive_skill(cfg: GUIConfig, skill_name: str, user_text: str, message_id: str) -> None:
    try:
        from crew import skill_registry
        from crew.direct import run_direct
        from crew.streamer import CallbackStreamer
    except ImportError as exc:
        await publish("chat_error", {"message_id": message_id, "detail": str(exc)})
        return
    try:
        skill = skill_registry.load_skill(skill_name)
    except skill_registry.SkillNotFound:
        await publish("chat_error", {"message_id": message_id, "detail": f"unknown skill: /{skill_name}"})
        return
    await _stream(
        run_direct(user_text, model=cfg.model, skill_prompt=skill.instructions, streamer=CallbackStreamer(on_delta_fn=_publisher(message_id))),
        message_id,
    )


async def _drive_agent(cfg: GUIConfig, agent_name: str, user_text: str, message_id: str) -> None:
    try:
        from crew import agent_registry
        from crew.direct import run_direct
        from crew.streamer import CallbackStreamer
    except ImportError as exc:
        await publish("chat_error", {"message_id": message_id, "detail": str(exc)})
        return
    try:
        agent = agent_registry.load_agent(agent_name)
    except agent_registry.AgentNotFound:
        await publish("chat_error", {"message_id": message_id, "detail": f"unknown agent: {agent_name}"})
        return
    await _stream(
        run_direct(user_text, model=cfg.model, agent_prompt=agent.prompt, streamer=CallbackStreamer(on_delta_fn=_publisher(message_id))),
        message_id,
    )


async def _drive_pipeline(cfg: GUIConfig, pipeline_name: str, user_text: str, message_id: str) -> None:
    try:
        from crew import pipeline_registry, pipeline_runner
        from crew.streamer import CallbackStreamer
    except ImportError as exc:
        await publish("chat_error", {"message_id": message_id, "detail": str(exc)})
        return

    # Daily-standup reuses the standup_service lock so a pipeline click
    # doesn't race with the "Regenerate" button.
    if pipeline_name == "daily-standup" and standup_service.is_running():
        await publish(
            "chat_error",
            {"message_id": message_id, "detail": "daily-standup already running"},
        )
        return

    try:
        config = pipeline_registry.load_pipeline(pipeline_name)
    except pipeline_registry.PipelineNotFound:
        await publish("chat_error", {"message_id": message_id, "detail": f"unknown pipeline: /{pipeline_name}"})
        return

    streamer = CallbackStreamer(on_delta_fn=_publisher(message_id))
    try:
        await pipeline_runner.run_pipeline(
            config,
            user_text or f"Run the {pipeline_name} pipeline.",
            model=cfg.model,
            crew_home=cfg.crew_home,
            streamer=streamer,
        )
    except Exception as exc:
        _log.exception("pipeline %r failed", pipeline_name)
        await publish("chat_error", {"message_id": message_id, "detail": str(exc)})
        return

    await publish("chat_done", {"message_id": message_id, "text": streamer.text.strip()})


async def _stream(run_coro, message_id: str) -> None:
    try:
        result = await run_coro
    except Exception as exc:
        _log.exception("pinned direct call failed")
        await publish("chat_error", {"message_id": message_id, "detail": str(exc)})
        return
    await publish("chat_done", {"message_id": message_id, "text": result.assistant_text})


def _publisher(message_id: str):
    loop = asyncio.get_event_loop()

    def _pub(text: str) -> None:
        coro = publish("chat_token", {"message_id": message_id, "delta": text})
        try:
            asyncio.ensure_future(coro, loop=loop)
        except RuntimeError:
            pass

    return _pub
