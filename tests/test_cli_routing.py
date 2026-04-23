"""CLI dispatch tests.

The router, runner, and direct helpers are fully mocked so we can assert
which dispatch path each flag combo takes without touching the SDK.
"""

from __future__ import annotations

import pathlib

import pytest

from crew import (
    agent_registry,
    cli,
    intent_router,
    pipeline_registry,
    pipeline_runner,
    skill_registry,
)
from crew.intent_router import RouteResult


class _Spy:
    def __init__(self):
        self.called_with: list[tuple[tuple, dict]] = []

    async def __call__(self, *args, **kwargs):
        self.called_with.append((args, kwargs))


def _fake_pipeline_config(name: str):
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


def _fake_agent_config(name: str, prompt: str = "persona-prompt"):
    return agent_registry.AgentConfig(
        name=name,
        description="fake",
        prompt=prompt,
        model=None,
        allowed_tools=[],
        frontmatter={},
        path=pathlib.Path("/tmp/agents/coder.md"),
        standalone=True,
        subagent_enabled=False,
        subagent_infer=False,
        raw={},
    )


@pytest.fixture
def spies(monkeypatch):
    direct_spy = _Spy()
    runner_spy = _Spy()
    router_spy = _Spy()

    async def router_stub(user_input, pipelines, agents=None, **kwargs):
        router_spy.called_with.append(((user_input, pipelines, agents), kwargs))
        return router_stub.verdict

    router_stub.verdict = RouteResult(mode="direct")

    monkeypatch.setattr(cli, "run_direct", direct_spy)
    monkeypatch.setattr(pipeline_runner, "run_level_0", runner_spy)
    monkeypatch.setattr(cli, "pipeline_runner", pipeline_runner)
    monkeypatch.setattr(intent_router, "route", router_stub)
    monkeypatch.setattr(cli, "intent_router", intent_router)
    monkeypatch.setattr(
        pipeline_registry,
        "discover",
        lambda *a, **k: [
            pipeline_registry.PipelineInfo(
                name="daily-standup",
                description="standup",
                level=0,
                path=pathlib.Path("/tmp/d"),
            )
        ],
    )

    def _load_pipeline(name, **kw):
        if name == "daily-standup":
            return _fake_pipeline_config(name)
        raise pipeline_registry.PipelineNotFound(name)

    monkeypatch.setattr(pipeline_registry, "load_pipeline", _load_pipeline)
    monkeypatch.setattr(
        agent_registry,
        "discover",
        lambda *a, **k: [
            agent_registry.AgentInfo(
                name="coder",
                description="coder",
                standalone=True,
                subagent_enabled=False,
                path=pathlib.Path("/tmp/agents/coder.md"),
            ),
            agent_registry.AgentInfo(
                name="internal-only",
                description="subagent",
                standalone=False,
                subagent_enabled=True,
                path=pathlib.Path("/tmp/agents/internal.md"),
            ),
        ],
    )

    def _load_agent(name, **kw):
        if name == "coder":
            return _fake_agent_config(name)
        if name == "internal-only":
            return agent_registry.AgentConfig(
                name="internal-only",
                description="subagent",
                prompt="internal",
                model=None,
                allowed_tools=[],
                frontmatter={},
                path=pathlib.Path("/tmp/agents/internal.md"),
                standalone=False,
                subagent_enabled=True,
                subagent_infer=True,
                raw={},
            )
        raise agent_registry.AgentNotFound(name)

    monkeypatch.setattr(agent_registry, "load_agent", _load_agent)

    monkeypatch.setattr(
        skill_registry,
        "discover",
        lambda *a, **k: [
            skill_registry.SkillInfo(
                name="debug",
                description="debug skill",
                version="0.1.0",
                path=pathlib.Path("/tmp/skills/debug"),
            )
        ],
    )

    def _load_skill(name, **kw):
        if name == "debug":
            return skill_registry.SkillConfig(
                name="debug",
                description="debug skill",
                version="0.1.0",
                instructions="be-systematic-about-debugging",
                allowed_tools=["read", "shell"],
                frontmatter={},
                path=pathlib.Path("/tmp/skills/debug/SKILL.md"),
                dir=pathlib.Path("/tmp/skills/debug"),
                references_dir=None,
                scripts_dir=None,
                raw={},
            )
        raise skill_registry.SkillNotFound(name)

    monkeypatch.setattr(skill_registry, "load_skill", _load_skill)

    return dict(
        direct=direct_spy,
        runner=runner_spy,
        router=router_spy,
        router_stub=router_stub,
    )


def test_direct_flag_skips_router(spies):
    rc = cli.main(["--direct", "hello"])
    assert rc == 0
    assert spies["direct"].called_with == [(("hello",), {"model": None})]
    assert spies["router"].called_with == []
    assert spies["runner"].called_with == []


def test_agent_flag_skips_router(spies):
    rc = cli.main(["--agent", "coder", "fix bug"])
    assert rc == 0
    assert len(spies["direct"].called_with) == 1
    (args, kwargs) = spies["direct"].called_with[0]
    assert args == ("fix bug",)
    assert kwargs["agent_prompt"] == "persona-prompt"
    assert spies["router"].called_with == []
    assert spies["runner"].called_with == []


def test_router_direct_verdict_dispatches_to_direct(spies):
    spies["router_stub"].verdict = RouteResult(mode="direct", reason="simple")
    rc = cli.main(["what time is it?"])
    assert rc == 0
    assert len(spies["router"].called_with) == 1
    (_args, kwargs) = spies["router"].called_with[0]
    assert "require_pipeline" not in kwargs or kwargs["require_pipeline"] is False
    assert spies["direct"].called_with == [(("what time is it?",), {"model": None})]
    assert spies["runner"].called_with == []


def test_router_agent_verdict_dispatches_to_direct_with_persona(spies):
    spies["router_stub"].verdict = RouteResult(
        mode="agent", agent="coder", reason="coding request"
    )
    rc = cli.main(["fix the flaky test"])
    assert rc == 0
    assert len(spies["router"].called_with) == 1
    assert len(spies["direct"].called_with) == 1
    (args, kwargs) = spies["direct"].called_with[0]
    assert args == ("fix the flaky test",)
    assert kwargs["agent_prompt"] == "persona-prompt"
    assert spies["runner"].called_with == []


def test_router_pipeline_verdict_dispatches_to_runner(spies):
    spies["router_stub"].verdict = RouteResult(
        mode="pipeline",
        pipeline="daily-standup",
        params={"date": "yesterday"},
        reason="standup match",
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
        mode="pipeline", pipeline="daily-standup", reason="forced"
    )
    rc = cli.main(["--pipeline", "hello"])
    assert rc == 0
    assert len(spies["router"].called_with) == 1
    (_args, kwargs) = spies["router"].called_with[0]
    assert kwargs.get("require_pipeline") is True
    assert len(spies["runner"].called_with) == 1


def test_mode_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli.main(["--direct", "--pipeline", "x"])
    with pytest.raises(SystemExit):
        cli.main(["--direct", "--agent", "coder", "x"])
    with pytest.raises(SystemExit):
        cli.main(["--pipeline", "--agent", "coder", "x"])


# ── Slash command dispatch (skills) ──────────────────────────────────────────


def test_slash_skill_invokes_direct_with_skill_prompt(spies):
    rc = cli.main(["/debug", "why", "is", "my", "test", "failing"])
    assert rc == 0
    # Router is never invoked — zero LLM cost.
    assert spies["router"].called_with == []
    assert spies["runner"].called_with == []
    assert len(spies["direct"].called_with) == 1
    (args, kwargs) = spies["direct"].called_with[0]
    # The skill's name is stripped; the rest is the user input.
    assert args == ("why is my test failing",)
    assert kwargs["skill_prompt"] == "be-systematic-about-debugging"
    # No agent persona is applied by a bare slash command.
    assert kwargs.get("agent_prompt") is None


def test_slash_skill_with_no_args_sends_empty_prompt(spies):
    rc = cli.main(["/debug"])
    assert rc == 0
    assert len(spies["direct"].called_with) == 1
    (args, kwargs) = spies["direct"].called_with[0]
    assert args == ("",)
    assert kwargs["skill_prompt"] == "be-systematic-about-debugging"


def test_slash_unknown_skill_exits_nonzero(spies, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["/nope", "something"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "unknown skill: /nope" in err
    assert "/debug" in err


def test_slash_does_not_dispatch_to_pipeline_or_agent(spies, capsys):
    # Even though `daily-standup` and `coder` exist, they are NOT
    # addressable via slash — slash is skill-only.
    with pytest.raises(SystemExit):
        cli.main(["/daily-standup", "prep"])
    assert spies["runner"].called_with == []

    capsys.readouterr()  # drain

    with pytest.raises(SystemExit):
        cli.main(["/coder", "fix"])
    assert spies["direct"].called_with == []


def test_direct_flag_sends_slash_prompt_verbatim(spies):
    # `--direct "/debug"` should NOT parse the slash — explicit override wins.
    rc = cli.main(["--direct", "/debug"])
    assert rc == 0
    assert spies["direct"].called_with == [(("/debug",), {"model": None})]
    assert spies["runner"].called_with == []
    assert spies["router"].called_with == []


def test_pipeline_flag_with_slash_still_uses_router(spies):
    spies["router_stub"].verdict = RouteResult(
        mode="pipeline", pipeline="daily-standup", reason="forced"
    )
    rc = cli.main(["--pipeline", "/debug"])
    assert rc == 0
    # Router IS called because --pipeline was passed; slash is ignored.
    assert len(spies["router"].called_with) == 1
    assert len(spies["runner"].called_with) == 1


# ── /help built-in ───────────────────────────────────────────────────────────


def test_slash_help_prints_registry_and_skips_sdk(spies, capsys):
    rc = cli.main(["/help"])
    assert rc == 0
    # No SDK call on any path.
    assert spies["direct"].called_with == []
    assert spies["router"].called_with == []
    assert spies["runner"].called_with == []

    out = capsys.readouterr().out
    # All three sections appear, populated from the mocked discoveries.
    assert "Pipelines" in out
    assert "daily-standup" in out
    assert "Level 0" in out
    assert "Agents" in out
    assert "coder" in out
    # Non-standalone agents are filtered out.
    assert "internal-only" not in out
    assert "Skills" in out
    assert "/debug" in out


def test_slash_help_extra_args_ignored(spies, capsys):
    # `/help anything else` still prints the registry — extra args are no-ops
    # because /help is a deterministic dispatcher, not a skill.
    rc = cli.main(["/help", "pipelines"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Pipelines" in out
    assert spies["direct"].called_with == []


def test_slash_unknown_skill_advertises_help(spies, capsys):
    with pytest.raises(SystemExit):
        cli.main(["/nope"])
    err = capsys.readouterr().err
    assert "/help" in err


def test_slash_help_works_with_empty_skill_registry(monkeypatch, spies, capsys):
    monkeypatch.setattr(skill_registry, "discover", lambda *a, **k: [])
    rc = cli.main(["/help"])
    assert rc == 0
    out = capsys.readouterr().out
    # Pipelines + agents still listed; skills section is shown but empty.
    assert "daily-standup" in out
    assert "(none registered" in out
