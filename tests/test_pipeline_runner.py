import asyncio
import json
from pathlib import Path

import pytest

from crew import hooks, pipeline_registry, pipeline_runner
from fake_copilot import make_fake_copilot_client


FIXTURES_PIPELINES = Path(__file__).parent / "fixtures" / "pipelines"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_hooks():
    hooks.clear()
    yield
    hooks.clear()


def test_run_level_0_writes_output_and_plan(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pipeline_runner,
        "CopilotClient",
        make_fake_copilot_client(reply="## Yesterday\n- did things\n"),
    )

    config = pipeline_registry.load_pipeline(
        "demo", pipelines_dir=FIXTURES_PIPELINES, repo_root=tmp_path
    )
    result = _run(pipeline_runner.run_level_0(config, "standup prep", crew_home=tmp_path))

    assert result.output_path.exists()
    assert result.plan_path.exists()

    output_text = result.output_path.read_text()
    assert "## Yesterday" in output_text

    plan = json.loads(result.plan_path.read_text())
    assert plan["pipeline"] == "demo"
    assert plan["level"] == 0
    assert plan["user_input"] == "standup prep"
    assert plan["output_path"] == str(result.output_path)
    assert plan["session_id"] == result.session_id


def test_hooks_fire_in_order(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pipeline_runner,
        "CopilotClient",
        make_fake_copilot_client(reply="hello"),
    )

    events: list[str] = []
    hooks.clear()
    hooks.register("session-start", lambda **ctx: events.append("session-start"))
    hooks.register("post-run", lambda **ctx: events.append("post-run"))

    config = pipeline_registry.load_pipeline(
        "demo", pipelines_dir=FIXTURES_PIPELINES, repo_root=tmp_path
    )
    _run(pipeline_runner.run_level_0(config, "go", crew_home=tmp_path))

    # Our two registered hooks fire in the correct order (defaults were
    # cleared so ordering is deterministic).
    assert events == ["session-start", "post-run"]


def test_runner_rejects_non_level_0(tmp_path: Path) -> None:
    config = pipeline_registry.load_pipeline(
        "demo", pipelines_dir=FIXTURES_PIPELINES, repo_root=tmp_path
    )
    # Bypass dataclass frozen by creating a new config via replace.
    from dataclasses import replace

    level1 = replace(config, level=1)
    with pytest.raises(ValueError, match="level=1"):
        _run(pipeline_runner.run_level_0(level1, "x", crew_home=tmp_path))


def test_system_message_is_agent_prompt(monkeypatch, tmp_path: Path) -> None:
    factory = make_fake_copilot_client(reply="ok")
    monkeypatch.setattr(pipeline_runner, "CopilotClient", factory)

    config = pipeline_registry.load_pipeline(
        "demo", pipelines_dir=FIXTURES_PIPELINES, repo_root=tmp_path
    )
    _run(pipeline_runner.run_level_0(config, "go", crew_home=tmp_path))

    client = factory.clients[-1]
    session = client.sessions[-1]
    system = session.kwargs.get("system_message")
    assert system is not None
    assert system["mode"] == "replace"
    assert "demo generator" in system["content"].lower()
    # The user prompt is sent verbatim, not the agent prompt.
    assert session.sent == ["go"]
