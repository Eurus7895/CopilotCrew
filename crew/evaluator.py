"""Run the isolated evaluator session for a Level 1 pipeline.

Per CLAUDE.md "Separate evaluator session. Fresh context. No shared state.
Non-negotiable.": the evaluator runs in a brand-new ``CopilotClient`` with a
brand-new ``create_session`` and receives only the generated output text plus
the pipeline's schema/criteria. No skill, no MCP, no generator history, no
tools.

The evaluator returns a strict JSON verdict ``{status, issues, summary}``.
Invalid JSON does NOT raise — the parser falls back to ``status="fail"`` with
the raw text used as the fix instruction so the correction loop can keep
moving. Same defensive pattern as ``crew.intent_router``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from copilot import CopilotClient
from copilot.generated.session_events import SessionEvent, SessionEventType

_log = logging.getLogger("crew.evaluator")

VerdictStatus = Literal["pass", "fail", "escalate"]


@dataclass(frozen=True)
class EvaluatorIssue:
    severity: str
    description: str
    fix_instruction: str


@dataclass(frozen=True)
class EvaluatorVerdict:
    status: VerdictStatus
    issues: list[EvaluatorIssue] = field(default_factory=list)
    summary: str = ""
    raw: str = ""

    @property
    def fix_instructions(self) -> list[str]:
        instructions = [i.fix_instruction for i in self.issues if i.fix_instruction]
        if instructions:
            return instructions
        if self.status != "pass" and self.raw:
            return [self.raw]
        return []


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(reply: str) -> dict | None:
    stripped = _JSON_FENCE.sub("", reply).strip()
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


def _coerce_issue(item: Any) -> EvaluatorIssue | None:
    if not isinstance(item, dict):
        return None
    severity = str(item.get("severity") or "minor")
    description = str(item.get("description") or "").strip()
    fix_instruction = str(item.get("fix_instruction") or "").strip()
    if not description and not fix_instruction:
        return None
    return EvaluatorIssue(
        severity=severity,
        description=description,
        fix_instruction=fix_instruction,
    )


def _parse_verdict(raw: str) -> EvaluatorVerdict:
    data = _extract_json(raw)
    if data is None:
        _log.warning("evaluator returned non-JSON output; falling back to fail")
        return EvaluatorVerdict(
            status="fail",
            issues=[],
            summary="evaluator returned invalid JSON",
            raw=raw,
        )

    status = data.get("status")
    if status not in ("pass", "fail", "escalate"):
        _log.warning("evaluator returned unknown status %r; treating as fail", status)
        status = "fail"

    issues_raw = data.get("issues") or []
    issues: list[EvaluatorIssue] = []
    if isinstance(issues_raw, list):
        for entry in issues_raw:
            issue = _coerce_issue(entry)
            if issue is not None:
                issues.append(issue)

    summary = str(data.get("summary") or "").strip()

    return EvaluatorVerdict(status=status, issues=issues, summary=summary, raw=raw)


_USER_ENVELOPE = (
    "Evaluate the following generator output against the criteria above. "
    "Respond with JSON only — no prose, no Markdown, no code fences.\n\n"
    "<<<OUTPUT>>>\n{output}\n<<<END OUTPUT>>>\n"
)


def _build_system_message(evaluator_prompt: str, schema_text: str | None) -> dict[str, Any]:
    content = evaluator_prompt.strip()
    if schema_text:
        content = f"{content}\n\n## Schema / Criteria\n\n{schema_text.strip()}"
    return {"mode": "replace", "content": content}


async def evaluate(
    output_text: str,
    evaluator_prompt: str,
    schema_text: str | None = None,
    *,
    model: str | None = None,
) -> EvaluatorVerdict:
    """Run the evaluator in a fresh session and return the parsed verdict.

    The evaluator session:

    * uses a fresh ``CopilotClient`` (no shared state with the generator),
    * has ``enable_config_discovery=False`` (no MCP, no skills),
    * passes no permission handler (no tools at all),
    * captures deltas to a buffer (does NOT stream to stdout).
    """
    buffer: list[str] = []

    def on_event(event: SessionEvent) -> None:
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                buffer.append(delta)

    system_message = _build_system_message(evaluator_prompt, schema_text)
    user_message = _USER_ENVELOPE.format(output=output_text)

    async with CopilotClient() as client:
        async with await client.create_session(
            model=model,
            streaming=True,
            enable_config_discovery=False,
            system_message=system_message,
        ) as session:
            session.on(on_event)
            await session.send_and_wait(user_message)

    return _parse_verdict("".join(buffer))
