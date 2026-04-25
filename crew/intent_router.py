"""Classify a user request as `direct`, `agent:{name}`, or `pipeline:{name}`.

Per CLAUDE.md "Execution Modes / Intent Router": one Copilot SDK call that
returns a JSON verdict. Invalid JSON or an unknown agent / pipeline name
falls back to ``direct`` — the router must never raise at the user.

The router reuses the same ``CopilotClient``/``create_session`` pattern as
``crew.direct`` but:

* does NOT stream to stdout (deltas are collected into a buffer),
* does NOT attach MCP servers (classification is prompt-only,
  ``enable_config_discovery=False``),
* passes the system prompt via ``system_message={"mode": "replace", ...}``
  so the classifier instructions are not diluted by SDK defaults.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from copilot import CopilotClient
from copilot.session import PermissionHandler

from crew.agent_registry import AgentInfo
from crew.pipeline_registry import PipelineInfo
from crew.streamer import Streamer

_log = logging.getLogger("crew.intent_router")

Mode = Literal["direct", "agent", "pipeline"]


@dataclass(frozen=True)
class RouteResult:
    mode: Mode
    pipeline: str | None = None
    agent: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    raw: str = ""


_SYSTEM_TEMPLATE = """\
You are Crew's intent router. Classify ONE user request as `direct`,
`agent`, or `pipeline`.

- `direct` — a simple question, explanation, lookup, or anything answerable
  in a single LLM call by a generic assistant. MCP is available.
- `agent` — the request clearly benefits from one of the standalone agents
  below. Agents are a persona-swap: one LLM call (like `direct`) but with
  the agent's prompt. Pick this when the task matches an agent's
  description better than the generic assistant.
- `pipeline` — the request matches one of the registered pipelines below.
  Pipelines are governed workflows (plan JSON + output file).

Match on intent, not keyword overlap.

{agent_block}
{pipeline_block}

Return ONLY a compact JSON object. No prose, no Markdown, no code fences.
Schema:
  {{"mode": "direct" | "agent" | "pipeline",
    "agent": "<agent-name or null>",
    "pipeline": "<pipeline-name or null>",
    "params": {{}},
    "reason": "<<=20 words>"}}

Rules:
- Exactly one of `agent` / `pipeline` is non-null, matching the chosen mode.
- If mode is "direct", both `agent` and `pipeline` MUST be null.
- If mode is "agent", `agent` MUST be the exact name of a standalone agent.
- If mode is "pipeline", `pipeline` MUST be the exact name of a pipeline.
- When nothing matches clearly, prefer "direct".
{forced}
"""

_FORCED_PIPELINE_CLAUSE = (
    "- The user has forced pipeline mode: you MUST return mode=\"pipeline\" "
    "and pick the best-matching registered pipeline."
)


def _build_agent_block(agents: list[AgentInfo]) -> str:
    if not agents:
        return "Standalone agents: (none registered)"
    lines = [f"- {a.name} — {a.description}" for a in agents if a.standalone]
    if not lines:
        return "Standalone agents: (none registered)"
    return "Standalone agents (persona swap, one LLM call, no output file):\n" + "\n".join(lines)


def _build_pipeline_block(pipelines: list[PipelineInfo]) -> str:
    if not pipelines:
        return "Registered pipelines: (none registered)"
    lines = [f"- {p.name} — {p.description}" for p in pipelines]
    return "Registered pipelines (governed workflow, plan JSON + output file):\n" + "\n".join(lines)


def _build_system_prompt(
    pipelines: list[PipelineInfo],
    agents: list[AgentInfo],
    *,
    require_pipeline: bool,
) -> str:
    return _SYSTEM_TEMPLATE.format(
        agent_block=_build_agent_block(agents),
        pipeline_block=_build_pipeline_block(pipelines),
        forced=("\n" + _FORCED_PIPELINE_CLAUSE) if require_pipeline else "",
    )


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(reply: str) -> dict | None:
    stripped = _JSON_FENCE.sub("", reply).strip()
    # Pull the first {...} block if the model padded with prose anyway.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    candidate = stripped[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _validate(
    data: dict,
    pipelines: list[PipelineInfo],
    agents: list[AgentInfo],
    *,
    require_pipeline: bool,
) -> tuple[RouteResult | None, str]:
    """Return (result, fallback_reason). Result is None → caller must fall back."""
    mode = data.get("mode")
    pipeline = data.get("pipeline")
    agent = data.get("agent")
    params = data.get("params") or {}
    reason = str(data.get("reason") or "")

    if not isinstance(params, dict):
        params = {}

    known_pipelines = {p.name for p in pipelines}
    known_agents = {a.name for a in agents if a.standalone}

    if mode == "direct":
        if require_pipeline:
            return None, "router returned direct under require_pipeline"
        return (
            RouteResult(mode="direct", pipeline=None, agent=None, params=params, reason=reason),
            "",
        )

    if mode == "pipeline":
        if not isinstance(pipeline, str):
            return None, "pipeline field missing or non-string"
        if pipeline not in known_pipelines:
            return None, f"unknown pipeline {pipeline!r}"
        return (
            RouteResult(
                mode="pipeline",
                pipeline=pipeline,
                agent=None,
                params=params,
                reason=reason,
            ),
            "",
        )

    if mode == "agent":
        if require_pipeline:
            return None, "router returned agent under require_pipeline"
        if not isinstance(agent, str):
            return None, "agent field missing or non-string"
        if agent not in known_agents:
            return None, f"unknown agent {agent!r}"
        return (
            RouteResult(
                mode="agent",
                pipeline=None,
                agent=agent,
                params=params,
                reason=reason,
            ),
            "",
        )

    return None, f"unknown mode {mode!r}"


def _fallback(
    pipelines: list[PipelineInfo],
    *,
    require_pipeline: bool,
    raw: str,
    cause: str,
) -> RouteResult:
    reason = f"router_fallback:{cause}"
    if require_pipeline and pipelines:
        return RouteResult(
            mode="pipeline",
            pipeline=pipelines[0].name,
            agent=None,
            params={},
            reason=reason,
            raw=raw,
        )
    return RouteResult(
        mode="direct", pipeline=None, agent=None, params={}, reason=reason, raw=raw
    )


async def _call_router(
    system_prompt: str,
    user_input: str,
    *,
    model: str | None,
) -> str:
    streamer = Streamer(mode="silent")

    async with CopilotClient() as client:
        async with await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=model,
            streaming=True,
            enable_config_discovery=False,
            system_message={"mode": "replace", "content": system_prompt},
        ) as session:
            session.on(streamer.handler)
            await session.send_and_wait(user_input)
    return streamer.finish()


async def route(
    user_input: str,
    pipelines: list[PipelineInfo],
    agents: list[AgentInfo] | None = None,
    *,
    model: str | None = None,
    require_pipeline: bool = False,
) -> RouteResult:
    """Return a ``RouteResult`` for ``user_input``.

    Never raises. On any classifier failure, returns a fallback
    (``direct`` normally, first pipeline under ``require_pipeline``).
    """
    agents = agents or []
    standalone_agents = [a for a in agents if a.standalone]

    # Fast-path: nothing to route to → skip the SDK call entirely.
    if not pipelines and not standalone_agents and not require_pipeline:
        return RouteResult(
            mode="direct",
            pipeline=None,
            agent=None,
            params={},
            reason="nothing to route to",
            raw="",
        )

    system_prompt = _build_system_prompt(
        pipelines, standalone_agents, require_pipeline=require_pipeline
    )
    try:
        raw = await _call_router(system_prompt, user_input, model=model)
    except Exception as exc:
        _log.warning("router call failed: %s: %s", type(exc).__name__, exc)
        return _fallback(
            pipelines,
            require_pipeline=require_pipeline,
            raw="",
            cause=f"call_failed:{type(exc).__name__}",
        )

    data = _extract_json(raw)
    if data is None:
        return _fallback(
            pipelines, require_pipeline=require_pipeline, raw=raw, cause="invalid_json"
        )

    result, cause = _validate(
        data, pipelines, standalone_agents, require_pipeline=require_pipeline
    )
    if result is None:
        return _fallback(pipelines, require_pipeline=require_pipeline, raw=raw, cause=cause)
    return RouteResult(
        mode=result.mode,
        pipeline=result.pipeline,
        agent=result.agent,
        params=result.params,
        reason=result.reason,
        raw=raw,
    )
