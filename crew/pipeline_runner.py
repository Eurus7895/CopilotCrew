"""Level 0 pipeline execution — single generator, no evaluator.

Per CLAUDE.md "Agent Complexity Model / Level 0":
* baseline checks, skill injection, plan JSON, hooks fire
* no evaluator, no schema validation, no correction loop

The runner is the one place hooks fire around the generator session.
"session-start" fires before the SDK session is created; "post-run" fires
after the output file has been written. "pre-tool-use" / "post-tool-use"
are dispatched from the session ``on_event`` callback when the installed
SDK exposes tool-use event types (gracefully absent otherwise).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from copilot import CopilotClient
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.session import PermissionHandler

from crew import hooks
from crew.pipeline_registry import PipelineConfig

_log = logging.getLogger("crew.pipeline_runner")


@dataclass
class RunResult:
    session_id: str
    output_path: Path
    plan_path: Path


_TOOL_USE_START = getattr(SessionEventType, "TOOL_EXECUTION_START", None)
_TOOL_USE_END = getattr(SessionEventType, "TOOL_EXECUTION_COMPLETE", None)
_TOOL_USE_WARNED = False


def _resolve_crew_home(crew_home: Path | None) -> Path:
    if crew_home is not None:
        return Path(crew_home)
    env = os.environ.get("CREW_HOME")
    if env:
        return Path(env)
    return Path.home() / ".crew"


def _iso_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_session_id(pipeline_name: str) -> str:
    return f"{pipeline_name}-{_iso_timestamp()}-{uuid.uuid4().hex[:6]}"


def _tool_use_warn_once() -> None:
    global _TOOL_USE_WARNED
    if _TOOL_USE_WARNED:
        return
    _TOOL_USE_WARNED = True
    _log.info(
        "installed copilot SDK does not expose TOOL_EXECUTION_{START,COMPLETE}; "
        "pre-tool-use/post-tool-use hooks will not fire until the SDK "
        "surfaces those events."
    )


async def run_level_0(
    config: PipelineConfig,
    user_input: str,
    params: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    crew_home: Path | None = None,
    route_result: dict[str, Any] | None = None,
) -> RunResult:
    if config.level != 0:
        raise ValueError(
            f"run_level_0 called with level={config.level}. "
            "Level 1+ execution lands on Day 3."
        )
    params = dict(params or {})

    home = _resolve_crew_home(crew_home)
    outputs_dir = home / "outputs" / config.output_subdir
    plans_dir = home / "plans"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    plans_dir.mkdir(parents=True, exist_ok=True)

    session_id = _build_session_id(config.name)
    output_path = outputs_dir / f"{_iso_timestamp()}-{uuid.uuid4().hex[:4]}.md"
    plan_path = plans_dir / f"{session_id}.json"

    started_at = _now_iso()
    hooks.fire(
        "session-start",
        session_id=session_id,
        pipeline=config.name,
        level=config.level,
        user_input=user_input,
    )

    buffer: list[str] = []

    def on_event(event: SessionEvent) -> None:
        etype = event.type
        if etype == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                sys.stdout.write(delta)
                sys.stdout.flush()
                buffer.append(delta)
            return
        if _TOOL_USE_START is not None and etype == _TOOL_USE_START:
            hooks.fire(
                "pre-tool-use",
                session_id=session_id,
                pipeline=config.name,
                event=event,
            )
            return
        if _TOOL_USE_END is not None and etype == _TOOL_USE_END:
            hooks.fire(
                "post-tool-use",
                session_id=session_id,
                pipeline=config.name,
                event=event,
            )
            return

    if _TOOL_USE_START is None or _TOOL_USE_END is None:
        _tool_use_warn_once()

    # MCP servers come from `.mcp.json` via the SDK's config discovery; the
    # pipeline's declared `mcp` list is recorded in the plan JSON for audit
    # but not passed to the SDK directly — the 0.2.2 `MCPServerConfig` shape
    # diverges from `.mcp.json` (requires an explicit `tools` list) and
    # wiring a translator is a Day 3+ concern.
    session_kwargs: dict[str, Any] = {
        "on_permission_request": PermissionHandler.approve_all,
        "model": model,
        "streaming": True,
        "enable_config_discovery": True,
        "system_message": {"mode": "replace", "content": config.agent_prompt.strip()},
    }

    async with CopilotClient() as client:
        async with await client.create_session(**session_kwargs) as session:
            session.on(on_event)
            await session.send_and_wait(user_input)

    sys.stdout.write("\n")
    sys.stdout.flush()

    output_text = "".join(buffer).strip() + "\n"
    output_path.write_text(output_text, encoding="utf-8")

    finished_at = _now_iso()
    plan_doc = {
        "session_id": session_id,
        "pipeline": config.name,
        "level": config.level,
        "user_input": user_input,
        "params": params,
        "route_result": route_result,
        "agent_path": str(config.agent_path),
        "mcp_servers": sorted(config.mcp_servers.keys()),
        "allowed_tools": config.allowed_tools,
        "started_at": started_at,
        "finished_at": finished_at,
        "output_path": str(output_path),
    }
    plan_path.write_text(json.dumps(plan_doc, indent=2) + "\n", encoding="utf-8")

    hooks.fire(
        "post-run",
        session_id=session_id,
        pipeline=config.name,
        output_path=str(output_path),
        plan_path=str(plan_path),
    )

    return RunResult(session_id=session_id, output_path=output_path, plan_path=plan_path)
