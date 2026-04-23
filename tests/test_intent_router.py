"""Tests for crew.intent_router.

The Copilot SDK is monkeypatched so tests never touch the network.
"""

import asyncio
from pathlib import Path

import pytest

from crew import intent_router
from crew.agent_registry import AgentInfo
from crew.pipeline_registry import PipelineInfo
from fake_copilot import make_fake_copilot_client


PIPELINES = [
    PipelineInfo(
        name="daily-standup",
        description="Prepare a daily standup summary.",
        level=0,
        path=Path("/tmp/daily-standup"),
    ),
]

AGENTS = [
    AgentInfo(
        name="coder",
        description="Focused coding agent; writes diffs.",
        standalone=True,
        subagent_enabled=False,
        path=Path("/tmp/agents/coder.md"),
    ),
    AgentInfo(
        name="subagent-only",
        description="Not offered to the user.",
        standalone=False,
        subagent_enabled=True,
        path=Path("/tmp/agents/subagent-only.md"),
    ),
]


def _run(coro):
    return asyncio.run(coro)


def test_direct_verdict(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"direct","pipeline":null,"agent":null,"params":{},"reason":"simple question"}'
        ),
    )
    result = _run(intent_router.route("what is 2+2?", PIPELINES, AGENTS))
    assert result.mode == "direct"
    assert result.pipeline is None
    assert result.agent is None
    assert result.reason == "simple question"


def test_pipeline_verdict(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"pipeline","pipeline":"daily-standup","agent":null,"params":{"date":"yesterday"},"reason":"standup"}'
        ),
    )
    result = _run(intent_router.route("standup prep", PIPELINES, AGENTS))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"
    assert result.agent is None
    assert result.params == {"date": "yesterday"}


def test_agent_verdict(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"agent","agent":"coder","pipeline":null,"params":{},"reason":"coding request"}'
        ),
    )
    result = _run(intent_router.route("fix the flaky test", PIPELINES, AGENTS))
    assert result.mode == "agent"
    assert result.agent == "coder"
    assert result.pipeline is None


def test_invalid_json_falls_back_to_direct(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(reply="not json at all"),
    )
    result = _run(intent_router.route("anything", PIPELINES, AGENTS))
    assert result.mode == "direct"
    assert result.reason.startswith("router_fallback:invalid_json")


def test_unknown_pipeline_falls_back_to_direct(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"pipeline","pipeline":"not-real","agent":null,"params":{},"reason":"x"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES, AGENTS))
    assert result.mode == "direct"
    assert "unknown pipeline" in result.reason


def test_unknown_agent_falls_back_to_direct(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"agent","agent":"ghost","pipeline":null,"params":{},"reason":"x"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES, AGENTS))
    assert result.mode == "direct"
    assert "unknown agent" in result.reason


def test_subagent_only_agent_is_not_selectable(monkeypatch) -> None:
    # Router returns `subagent-only` — it exists but standalone=False, so must fall back.
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"agent","agent":"subagent-only","pipeline":null,"params":{},"reason":"x"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES, AGENTS))
    assert result.mode == "direct"
    assert "unknown agent" in result.reason


def test_json_inside_code_fence_is_parsed(monkeypatch) -> None:
    reply = (
        "```json\n"
        '{"mode":"pipeline","pipeline":"daily-standup","agent":null,"params":{},"reason":"ok"}\n'
        "```"
    )
    monkeypatch.setattr(
        intent_router, "CopilotClient", make_fake_copilot_client(reply=reply)
    )
    result = _run(intent_router.route("standup prep", PIPELINES, AGENTS))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"


def test_require_pipeline_picks_first_when_router_says_direct(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"direct","pipeline":null,"agent":null,"params":{},"reason":"simple"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES, AGENTS, require_pipeline=True))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"


def test_require_pipeline_rejects_agent_verdict(monkeypatch) -> None:
    # Router returns agent; under require_pipeline we must fall back to the first pipeline.
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"agent","agent":"coder","pipeline":null,"params":{},"reason":"x"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES, AGENTS, require_pipeline=True))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"


def test_empty_registries_short_circuit(monkeypatch) -> None:
    sentinel = {"called": False}

    def boom(*_a, **_kw):
        sentinel["called"] = True
        raise AssertionError("router should not be called")

    monkeypatch.setattr(intent_router, "CopilotClient", boom)
    result = _run(intent_router.route("x", [], []))
    assert result.mode == "direct"
    assert sentinel["called"] is False


def test_empty_agents_preserves_two_way_behaviour(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"direct","pipeline":null,"agent":null,"params":{},"reason":"x"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES, []))
    assert result.mode == "direct"


def test_router_failure_falls_back(monkeypatch) -> None:
    def explode(*_a, **_kw):
        raise RuntimeError("sdk unavailable")

    monkeypatch.setattr(intent_router, "CopilotClient", explode)
    result = _run(intent_router.route("x", PIPELINES, AGENTS))
    assert result.mode == "direct"
    assert result.reason.startswith("router_fallback:call_failed")


def test_require_pipeline_on_router_failure(monkeypatch) -> None:
    def explode(*_a, **_kw):
        raise RuntimeError("sdk unavailable")

    monkeypatch.setattr(intent_router, "CopilotClient", explode)
    result = _run(intent_router.route("x", PIPELINES, AGENTS, require_pipeline=True))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"
