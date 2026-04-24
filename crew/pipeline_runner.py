"""Level 0 / Level 1 pipeline execution.

Per CLAUDE.md "Agent Complexity Model":

* Level 0 — single generator, no evaluator. Hooks fire (``session-start``,
  ``post-run``) and the plan JSON + output file are written.
* Level 1 — generator + isolated evaluator + correction loop. Up to
  ``max_retries`` attempts; ``on-eval-fail`` fires per failed verdict;
  ``on-escalate`` fires once when the loop exhausts. Each attempt's output
  is preserved on disk for audit; the plan JSON contains the full
  ``attempts`` array.

The evaluator runs in ``crew.evaluator.evaluate`` — a fresh
``CopilotClient`` per call with no MCP, no skills, no tools. See CLAUDE.md
"Separate evaluator session. Fresh context. No shared state. Non-negotiable."

``run_pipeline(config, ...)`` dispatches by ``config.level``. Level 2+
is rejected (not in v1 per CLAUDE.md "Not Building in v1").
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from copilot import CopilotClient
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.session import PermissionHandler

from crew import evaluator as _evaluator
from crew import hooks
from crew.pipeline_registry import PipelineConfig
from crew.streamer import Streamer, TerminalStreamer

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


def _verdict_to_dict(verdict: _evaluator.EvaluatorVerdict) -> dict[str, Any]:
    return {
        "status": verdict.status,
        "summary": verdict.summary,
        "issues": [asdict(i) for i in verdict.issues],
    }


async def _run_generator(
    config: PipelineConfig,
    user_input: str,
    *,
    session_id: str,
    model: str | None,
    fix_instructions: list[str] | None = None,
    streamer: Streamer | None = None,
) -> tuple[str, str, str]:
    """Run one generator turn. Returns (output_text, started_at, finished_at).

    The user message is sent verbatim unless ``fix_instructions`` is
    provided, in which case a ``## Fix Instructions`` block is appended so
    the next attempt sees the evaluator's feedback. The system message is
    always ``config.agent_prompt`` — the generator restarts with a fresh
    session per attempt (no carry-over context).

    ``streamer`` chooses where deltas go. Default :class:`TerminalStreamer`
    prints to stdout (legacy behaviour). The GUI passes a
    :class:`CallbackStreamer` that fans deltas onto the SSE bus.
    """
    # pre-/post-tool-use hooks fire through the streamer so every caller
    # gets them — not just the default terminal path.
    hook_streamer = _HookFiringStreamer(
        inner=streamer or TerminalStreamer(),
        session_id=session_id,
        pipeline_name=config.name,
    )

    if _TOOL_USE_START is None or _TOOL_USE_END is None:
        _tool_use_warn_once()

    prompt = user_input
    if fix_instructions:
        joined = "\n".join(f"- {instr}" for instr in fix_instructions if instr)
        prompt = f"{user_input}\n\n## Fix Instructions\n\n{joined}\n"

    started_at = _now_iso()
    session_kwargs: dict[str, Any] = {
        "on_permission_request": PermissionHandler.approve_all,
        "model": model,
        "streaming": True,
        "enable_config_discovery": True,
        "system_message": {"mode": "replace", "content": config.agent_prompt.strip()},
    }
    async with CopilotClient() as client:
        async with await client.create_session(**session_kwargs) as session:
            session.on(hook_streamer.handle_event)
            await session.send_and_wait(prompt)
    hook_streamer.finish_line()
    finished_at = _now_iso()

    output_text = hook_streamer.text.strip() + "\n"
    return output_text, started_at, finished_at


class _HookFiringStreamer(Streamer):
    """Wraps another streamer; forwards deltas + fires pre/post-tool hooks.

    We inherit from ``Streamer`` instead of subclassing a concrete type so
    any caller-supplied streamer (Terminal, Callback, …) can be composed.
    """

    def __init__(self, *, inner: Streamer, session_id: str, pipeline_name: str) -> None:
        super().__init__()
        self._inner = inner
        self._session_id = session_id
        self._pipeline_name = pipeline_name

    def handle_event(self, event: SessionEvent) -> None:
        # Delegate to inner (which updates its own buffer and its on_delta),
        # then additionally dispatch tool-use events to the hook registry.
        self._inner.handle_event(event)
        etype = event.type
        if _TOOL_USE_START is not None and etype == _TOOL_USE_START:
            hooks.fire(
                "pre-tool-use",
                session_id=self._session_id,
                pipeline=self._pipeline_name,
                event=event,
            )
        elif _TOOL_USE_END is not None and etype == _TOOL_USE_END:
            hooks.fire(
                "post-tool-use",
                session_id=self._session_id,
                pipeline=self._pipeline_name,
                event=event,
            )

    @property
    def text(self) -> str:
        return self._inner.text

    def finish_line(self) -> None:
        self._inner.finish_line()


async def run_level_0(
    config: PipelineConfig,
    user_input: str,
    params: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    crew_home: Path | None = None,
    route_result: dict[str, Any] | None = None,
    streamer: Streamer | None = None,
) -> RunResult:
    if config.level != 0:
        raise ValueError(
            f"run_level_0 called with level={config.level}. "
            "Use run_pipeline(...) to dispatch by level — Level 1 lands via run_level_1."
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

    hooks.fire(
        "session-start",
        session_id=session_id,
        pipeline=config.name,
        level=config.level,
        user_input=user_input,
    )

    output_text, started_at, finished_at = await _run_generator(
        config, user_input, session_id=session_id, model=model, streamer=streamer
    )
    output_path.write_text(output_text, encoding="utf-8")

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


async def run_level_1(
    config: PipelineConfig,
    user_input: str,
    params: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    crew_home: Path | None = None,
    route_result: dict[str, Any] | None = None,
    max_retries: int = 3,
    streamer: Streamer | None = None,
) -> RunResult:
    if config.level != 1:
        raise ValueError(
            f"run_level_1 called with level={config.level}. "
            "Use run_pipeline(...) to dispatch by level."
        )
    if not config.evaluator_prompt:
        raise ValueError(
            f"pipeline {config.name!r} is Level 1 but has no evaluator prompt loaded"
        )
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    params = dict(params or {})

    home = _resolve_crew_home(crew_home)
    outputs_dir = home / "outputs" / config.output_subdir
    plans_dir = home / "plans"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    plans_dir.mkdir(parents=True, exist_ok=True)

    session_id = _build_session_id(config.name)
    plan_path = plans_dir / f"{session_id}.json"
    run_stamp = _iso_timestamp()
    run_uid = uuid.uuid4().hex[:4]

    hooks.fire(
        "session-start",
        session_id=session_id,
        pipeline=config.name,
        level=config.level,
        user_input=user_input,
    )

    attempts: list[dict[str, Any]] = []
    last_fix_instructions: list[str] | None = None
    final_output_path: Path | None = None
    final_verdict: _evaluator.EvaluatorVerdict | None = None
    escalated = False

    for attempt in range(1, max_retries + 1):
        output_text, started_at, finished_at = await _run_generator(
            config,
            user_input,
            session_id=session_id,
            model=model,
            fix_instructions=last_fix_instructions,
            streamer=streamer,
        )
        attempt_output_path = (
            outputs_dir / f"{run_stamp}-{run_uid}-attempt{attempt}.md"
        )
        attempt_output_path.write_text(output_text, encoding="utf-8")

        verdict = await _evaluator.evaluate(
            output_text,
            config.evaluator_prompt,
            config.schema_text,
            model=model,
        )
        final_verdict = verdict
        final_output_path = attempt_output_path
        attempts.append(
            {
                "attempt": attempt,
                "output_path": str(attempt_output_path),
                "started_at": started_at,
                "finished_at": finished_at,
                "verdict": _verdict_to_dict(verdict),
            }
        )

        if verdict.status == "pass":
            break

        hooks.fire(
            "on-eval-fail",
            session_id=session_id,
            pipeline=config.name,
            attempt=attempt,
            verdict=verdict,
        )

        if verdict.status == "escalate":
            escalated = True
            break

        if attempt >= max_retries:
            escalated = True
            break

        last_fix_instructions = verdict.fix_instructions

    if escalated:
        hooks.fire(
            "on-escalate",
            session_id=session_id,
            pipeline=config.name,
            attempts=attempts,
            verdict=final_verdict,
        )

    assert final_output_path is not None  # loop runs at least once
    plan_doc: dict[str, Any] = {
        "session_id": session_id,
        "pipeline": config.name,
        "level": config.level,
        "user_input": user_input,
        "params": params,
        "route_result": route_result,
        "agent_path": str(config.agent_path),
        "evaluator_path": str(config.evaluator_path) if config.evaluator_path else None,
        "schema_path": str(config.schema_path) if config.schema_path else None,
        "mcp_servers": sorted(config.mcp_servers.keys()),
        "allowed_tools": config.allowed_tools,
        "max_retries": max_retries,
        "attempts": attempts,
        "escalated": escalated,
        "final_output_path": str(final_output_path),
    }
    plan_path.write_text(json.dumps(plan_doc, indent=2) + "\n", encoding="utf-8")

    hooks.fire(
        "post-run",
        session_id=session_id,
        pipeline=config.name,
        output_path=str(final_output_path),
        plan_path=str(plan_path),
    )

    return RunResult(
        session_id=session_id, output_path=final_output_path, plan_path=plan_path
    )


async def run_pipeline(
    config: PipelineConfig,
    user_input: str,
    params: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    crew_home: Path | None = None,
    route_result: dict[str, Any] | None = None,
    max_retries: int = 3,
    streamer: Streamer | None = None,
) -> RunResult:
    """Dispatch by ``config.level``.

    Level 2+ is rejected — promotion to Level 2 is gated on observed
    Level 1 failures (CLAUDE.md "Agent Complexity Model").
    """
    if config.level == 0:
        return await run_level_0(
            config,
            user_input,
            params,
            model=model,
            crew_home=crew_home,
            route_result=route_result,
            streamer=streamer,
        )
    if config.level == 1:
        return await run_level_1(
            config,
            user_input,
            params,
            model=model,
            crew_home=crew_home,
            route_result=route_result,
            max_retries=max_retries,
            streamer=streamer,
        )
    raise ValueError(
        f"Level {config.level} not supported in v1 (Level 2 is gated on "
        "observed Level 1 failures — see CLAUDE.md)."
    )
