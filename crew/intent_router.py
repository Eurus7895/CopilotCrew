"""Classify a user request as `direct` or `pipeline:{name}`.

Per CLAUDE.md "Execution Modes / Intent Router": one Copilot SDK call that
returns a JSON verdict. Invalid JSON or an unknown pipeline name falls back
to ``direct`` — the router must never raise at the user.

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
from copilot.generated.session_events import SessionEvent, SessionEventType
from copilot.session import PermissionHandler

from crew.pipeline_registry import PipelineInfo

_log = logging.getLogger("crew.intent_router")

Mode = Literal["direct", "pipeline"]


@dataclass(frozen=True)
class RouteResult:
    mode: Mode
    pipeline: str | None
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    raw: str = ""


_SYSTEM_TEMPLATE = """\
You are Crew's intent router. Classify ONE user request as `direct` or
`pipeline`.

- `direct` — a simple question, explanation, lookup, or anything answerable
  in a single LLM call. MCP is available in direct mode for data lookups.
- `pipeline` — the request clearly matches one of the registered pipelines
  below. Match on intent, not keyword overlap.

Registered pipelines:
{pipeline_list}

Return ONLY a compact JSON object. No prose, no Markdown, no code fences.
Schema:
  {{"mode": "direct" | "pipeline",
    "pipeline": "<pipeline-name or null>",
    "params": {{}},
    "reason": "<<=20 words>"}}

Rules:
- If mode is "direct", pipeline MUST be null.
- If mode is "pipeline", pipeline MUST be the exact name of one of the
  registered pipelines above.
- If no pipeline matches, return mode="direct".
{forced}
"""

_FORCED_CLAUSE = (
    "- The user has forced pipeline mode: you MUST return mode=\"pipeline\" "
    "and pick the best-matching registered pipeline."
)


def _build_system_prompt(pipelines: list[PipelineInfo], *, require_pipeline: bool) -> str:
    if pipelines:
        lines = [f"- {p.name} — {p.description}" for p in pipelines]
        pipeline_list = "\n".join(lines)
    else:
        pipeline_list = "(none registered)"
    return _SYSTEM_TEMPLATE.format(
        pipeline_list=pipeline_list,
        forced=("\n" + _FORCED_CLAUSE) if require_pipeline else "",
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
    *,
    require_pipeline: bool,
) -> tuple[RouteResult | None, str]:
    """Return (result, fallback_reason). Result is None → caller must fall back."""
    mode = data.get("mode")
    pipeline = data.get("pipeline")
    params = data.get("params") or {}
    reason = str(data.get("reason") or "")

    if not isinstance(params, dict):
        params = {}

    if mode == "direct":
        if require_pipeline:
            return None, "router returned direct under require_pipeline"
        return RouteResult(mode="direct", pipeline=None, params=params, reason=reason), ""

    if mode == "pipeline":
        if not isinstance(pipeline, str):
            return None, "pipeline field missing or non-string"
        known = {p.name for p in pipelines}
        if pipeline not in known:
            return None, f"unknown pipeline {pipeline!r}"
        return RouteResult(mode="pipeline", pipeline=pipeline, params=params, reason=reason), ""

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
        # User forced pipeline mode; pick the first registered one.
        return RouteResult(
            mode="pipeline",
            pipeline=pipelines[0].name,
            params={},
            reason=reason,
            raw=raw,
        )
    return RouteResult(mode="direct", pipeline=None, params={}, reason=reason, raw=raw)


async def _call_router(
    system_prompt: str,
    user_input: str,
    *,
    model: str | None,
) -> str:
    buffer: list[str] = []

    def on_event(event: SessionEvent) -> None:
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                buffer.append(delta)

    async with CopilotClient() as client:
        async with await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=model,
            streaming=True,
            enable_config_discovery=False,
            system_message={"mode": "replace", "content": system_prompt},
        ) as session:
            session.on(on_event)
            await session.send_and_wait(user_input)
    return "".join(buffer)


async def route(
    user_input: str,
    pipelines: list[PipelineInfo],
    *,
    model: str | None = None,
    require_pipeline: bool = False,
) -> RouteResult:
    """Return a ``RouteResult`` for ``user_input``.

    Never raises. On any classifier failure, returns a fallback
    (``direct`` normally, first pipeline under ``require_pipeline``).
    """
    if not pipelines and not require_pipeline:
        return RouteResult(
            mode="direct",
            pipeline=None,
            params={},
            reason="no pipelines registered",
            raw="",
        )

    system_prompt = _build_system_prompt(pipelines, require_pipeline=require_pipeline)
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
        return _fallback(pipelines, require_pipeline=require_pipeline, raw=raw, cause="invalid_json")

    result, cause = _validate(data, pipelines, require_pipeline=require_pipeline)
    if result is None:
        return _fallback(pipelines, require_pipeline=require_pipeline, raw=raw, cause=cause)
    return RouteResult(
        mode=result.mode,
        pipeline=result.pipeline,
        params=result.params,
        reason=result.reason,
        raw=raw,
    )
