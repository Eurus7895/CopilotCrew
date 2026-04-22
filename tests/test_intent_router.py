"""Tests for crew.intent_router.

The Copilot SDK is monkeypatched so tests never touch the network.
"""

import asyncio
from pathlib import Path

import pytest

from crew import intent_router
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


def _run(coro):
    return asyncio.run(coro)


def test_direct_verdict(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(reply='{"mode":"direct","pipeline":null,"params":{},"reason":"simple question"}'),
    )
    result = _run(intent_router.route("what is 2+2?", PIPELINES))
    assert result.mode == "direct"
    assert result.pipeline is None
    assert result.reason == "simple question"


def test_pipeline_verdict(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"pipeline","pipeline":"daily-standup","params":{"date":"yesterday"},"reason":"standup"}'
        ),
    )
    result = _run(intent_router.route("standup prep", PIPELINES))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"
    assert result.params == {"date": "yesterday"}


def test_invalid_json_falls_back_to_direct(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(reply="not json at all"),
    )
    result = _run(intent_router.route("anything", PIPELINES))
    assert result.mode == "direct"
    assert result.reason.startswith("router_fallback:invalid_json")


def test_unknown_pipeline_falls_back_to_direct(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"pipeline","pipeline":"not-real","params":{},"reason":"x"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES))
    assert result.mode == "direct"
    assert "unknown pipeline" in result.reason


def test_json_inside_code_fence_is_parsed(monkeypatch) -> None:
    reply = (
        "```json\n"
        '{"mode":"pipeline","pipeline":"daily-standup","params":{},"reason":"ok"}\n'
        "```"
    )
    monkeypatch.setattr(
        intent_router, "CopilotClient", make_fake_copilot_client(reply=reply)
    )
    result = _run(intent_router.route("standup prep", PIPELINES))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"


def test_require_pipeline_picks_first_when_router_says_direct(monkeypatch) -> None:
    monkeypatch.setattr(
        intent_router,
        "CopilotClient",
        make_fake_copilot_client(
            reply='{"mode":"direct","pipeline":null,"params":{},"reason":"simple"}'
        ),
    )
    result = _run(intent_router.route("x", PIPELINES, require_pipeline=True))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"
    assert "require_pipeline" in result.reason


def test_empty_pipeline_list_short_circuits(monkeypatch) -> None:
    # No pipelines → no router call needed; returns direct without touching SDK.
    sentinel_called = {"flag": False}

    def boom(*_a, **_kw):
        sentinel_called["flag"] = True
        raise AssertionError("router should not be called")

    monkeypatch.setattr(intent_router, "CopilotClient", boom)
    result = _run(intent_router.route("x", []))
    assert result.mode == "direct"
    assert sentinel_called["flag"] is False


def test_router_failure_falls_back(monkeypatch) -> None:
    def explode(*_a, **_kw):
        raise RuntimeError("sdk unavailable")

    monkeypatch.setattr(intent_router, "CopilotClient", explode)
    result = _run(intent_router.route("x", PIPELINES))
    assert result.mode == "direct"
    assert result.reason.startswith("router_fallback:call_failed")


def test_require_pipeline_on_router_failure(monkeypatch) -> None:
    def explode(*_a, **_kw):
        raise RuntimeError("sdk unavailable")

    monkeypatch.setattr(intent_router, "CopilotClient", explode)
    result = _run(intent_router.route("x", PIPELINES, require_pipeline=True))
    assert result.mode == "pipeline"
    assert result.pipeline == "daily-standup"
