"""CLI dispatch tests. The router and runner are fully mocked so we can
assert which dispatch path each flag combo takes.
"""

from __future__ import annotations

import pytest

from crew import cli, intent_router, pipeline_registry, pipeline_runner
from crew.intent_router import RouteResult


class _Spy:
    def __init__(self):
        self.called_with: list[tuple[tuple, dict]] = []

    async def __call__(self, *args, **kwargs):
        self.called_with.append((args, kwargs))


@pytest.fixture
def spies(monkeypatch):
    direct_spy = _Spy()
    runner_spy = _Spy()
    router_spy = _Spy()

    async def router_stub(user_input, pipelines, **kwargs):
        router_spy.called_with.append(((user_input, pipelines), kwargs))
        # Default: hand back whatever pre-programmed verdict the test set.
        return router_stub.verdict

    router_stub.verdict = RouteResult(
        mode="direct", pipeline=None, params={}, reason="", raw=""
    )

    monkeypatch.setattr(cli, "run_direct", direct_spy)
    monkeypatch.setattr(pipeline_runner, "run_level_0", runner_spy)
    monkeypatch.setattr(cli, "pipeline_runner", pipeline_runner)
    monkeypatch.setattr(intent_router, "route", router_stub)
    monkeypatch.setattr(cli, "intent_router", intent_router)
    monkeypatch.setattr(
        pipeline_registry, "discover", lambda *a, **k: [
            pipeline_registry.PipelineInfo(
                name="daily-standup",
                description="standup",
                level=0,
                path=__import__("pathlib").Path("/tmp/d"),
            )
        ]
    )
    monkeypatch.setattr(
        pipeline_registry,
        "load_pipeline",
        lambda name, **kw: _fake_config(name),
    )

    return dict(
        direct=direct_spy,
        runner=runner_spy,
        router=router_spy,
        router_stub=router_stub,
    )


def _fake_config(name: str):
    import pathlib

    return pipeline_registry.PipelineConfig(
        name=name,
        level=0,
        description="fake",
        agent_path=pathlib.Path("/tmp/a.md"),
        agent_frontmatter={},
        agent_prompt="fake",
        mcp_servers={},
        allowed_tools=[],
        output_subdir=name,
        path=pathlib.Path("/tmp"),
        raw={},
    )


def test_direct_flag_skips_router(spies):
    rc = cli.main(["--direct", "hello"])
    assert rc == 0
    assert spies["direct"].called_with == [(("hello",), {"model": None})]
    assert spies["router"].called_with == []
    assert spies["runner"].called_with == []


def test_router_direct_verdict_dispatches_to_direct(spies):
    spies["router_stub"].verdict = RouteResult(
        mode="direct", pipeline=None, params={}, reason="simple", raw=""
    )
    rc = cli.main(["what time is it?"])
    assert rc == 0
    assert len(spies["router"].called_with) == 1
    assert spies["direct"].called_with == [(("what time is it?",), {"model": None})]
    assert spies["runner"].called_with == []


def test_router_pipeline_verdict_dispatches_to_runner(spies):
    spies["router_stub"].verdict = RouteResult(
        mode="pipeline",
        pipeline="daily-standup",
        params={"date": "yesterday"},
        reason="standup match",
        raw="",
    )
    rc = cli.main(["standup prep"])
    assert rc == 0
    assert len(spies["router"].called_with) == 1
    assert spies["direct"].called_with == []
    assert len(spies["runner"].called_with) == 1
    (args, kwargs) = spies["runner"].called_with[0]
    assert args[1] == "standup prep"
    assert args[2] == {"date": "yesterday"}
    assert kwargs["route_result"]["reason"] == "standup match"


def test_pipeline_flag_forces_require_pipeline(spies):
    spies["router_stub"].verdict = RouteResult(
        mode="pipeline", pipeline="daily-standup", params={}, reason="forced", raw=""
    )
    rc = cli.main(["--pipeline", "hello"])
    assert rc == 0
    # The router was called once with require_pipeline=True.
    assert len(spies["router"].called_with) == 1
    (_args, kwargs) = spies["router"].called_with[0]
    assert kwargs.get("require_pipeline") is True
    assert len(spies["runner"].called_with) == 1


def test_direct_and_pipeline_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli.main(["--direct", "--pipeline", "hello"])
