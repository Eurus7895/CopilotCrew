import asyncio
import json
from pathlib import Path

import pytest

from crew import evaluator, hooks, pipeline_registry, pipeline_runner
from fake_copilot import make_fake_copilot_client


FIXTURES_PIPELINES = Path(__file__).parent / "fixtures" / "pipelines"

_PASS_VERDICT = '{"status":"pass","issues":[],"summary":"ok"}'


def _fail_verdict(fix: str) -> str:
    return (
        '{"status":"fail","summary":"missing summary",'
        '"issues":[{"severity":"major","description":"no Summary heading",'
        f'"fix_instruction":"{fix}"}}]}}'
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_hooks():
    hooks.clear()
    yield
    hooks.clear()


def _patch_both_clients(monkeypatch, factory):
    """Both the runner and the evaluator import CopilotClient at module level."""
    monkeypatch.setattr(pipeline_runner, "CopilotClient", factory)
    monkeypatch.setattr(evaluator, "CopilotClient", factory)


def _capture_hooks() -> dict[str, list[dict]]:
    captured: dict[str, list[dict]] = {
        "session-start": [],
        "on-eval-fail": [],
        "on-escalate": [],
        "post-run": [],
    }

    def _make(name: str):
        def _handler(**ctx):
            captured[name].append(ctx)
        return _handler

    for name in captured:
        hooks.register(name, _make(name))
    return captured


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


# ── Level 1 ──────────────────────────────────────────────────────────────────


def _load_demo_l1(tmp_path: Path):
    return pipeline_registry.load_pipeline(
        "demo-l1", pipelines_dir=FIXTURES_PIPELINES, repo_root=tmp_path
    )


def test_run_level_1_pass_first_try(monkeypatch, tmp_path: Path) -> None:
    factory = make_fake_copilot_client(
        replies=["## Summary\nall good\n", _PASS_VERDICT]
    )
    _patch_both_clients(monkeypatch, factory)
    captured = _capture_hooks()

    config = _load_demo_l1(tmp_path)
    result = _run(pipeline_runner.run_level_1(config, "go", crew_home=tmp_path))

    # Two clients constructed: generator + evaluator.
    assert len(factory.clients) == 2
    plan = json.loads(result.plan_path.read_text())
    assert len(plan["attempts"]) == 1
    assert plan["attempts"][0]["verdict"]["status"] == "pass"
    assert plan["escalated"] is False
    assert plan["final_output_path"] == str(result.output_path)

    assert len(captured["on-eval-fail"]) == 0
    assert len(captured["on-escalate"]) == 0
    assert len(captured["post-run"]) == 1
    assert len(captured["session-start"]) == 1


def test_run_level_1_retry_then_pass(monkeypatch, tmp_path: Path) -> None:
    fix = "Add a `## Summary` heading."
    factory = make_fake_copilot_client(
        replies=[
            "missing summary header\n",
            _fail_verdict(fix),
            "## Summary\nfixed it\n",
            _PASS_VERDICT,
        ]
    )
    _patch_both_clients(monkeypatch, factory)
    captured = _capture_hooks()

    config = _load_demo_l1(tmp_path)
    result = _run(pipeline_runner.run_level_1(config, "go", crew_home=tmp_path))

    assert len(factory.clients) == 4  # gen, eval, gen-retry, eval-retry
    plan = json.loads(result.plan_path.read_text())
    assert len(plan["attempts"]) == 2
    assert plan["attempts"][0]["verdict"]["status"] == "fail"
    assert plan["attempts"][1]["verdict"]["status"] == "pass"
    assert plan["escalated"] is False

    # The second generator session received the fix instruction in its prompt.
    second_generator_client = factory.clients[2]
    second_generator_session = second_generator_client.sessions[-1]
    assert any(fix in sent for sent in second_generator_session.sent)

    assert len(captured["on-eval-fail"]) == 1
    assert captured["on-eval-fail"][0]["attempt"] == 1
    assert len(captured["on-escalate"]) == 0


def test_run_level_1_exhaustion_escalates(monkeypatch, tmp_path: Path) -> None:
    fix = "Add a `## Summary` heading."
    factory = make_fake_copilot_client(
        replies=[
            "no summary 1\n",
            _fail_verdict(fix),
            "no summary 2\n",
            _fail_verdict(fix),
            "no summary 3\n",
            _fail_verdict(fix),
        ]
    )
    _patch_both_clients(monkeypatch, factory)
    captured = _capture_hooks()

    config = _load_demo_l1(tmp_path)
    result = _run(
        pipeline_runner.run_level_1(
            config, "go", crew_home=tmp_path, max_retries=3
        )
    )

    assert len(factory.clients) == 6
    plan = json.loads(result.plan_path.read_text())
    assert len(plan["attempts"]) == 3
    assert plan["escalated"] is True
    assert plan["final_output_path"] == plan["attempts"][-1]["output_path"]
    assert plan["final_output_path"] == str(result.output_path)

    assert len(captured["on-eval-fail"]) == 3
    assert len(captured["on-escalate"]) == 1
    assert captured["on-escalate"][0]["pipeline"] == "demo-l1"
    assert captured["on-escalate"][0]["attempts"] == plan["attempts"]


def test_run_level_1_escalate_status_short_circuits(
    monkeypatch, tmp_path: Path
) -> None:
    factory = make_fake_copilot_client(
        replies=[
            "missing summary\n",
            '{"status":"escalate","issues":[],"summary":"give up"}',
        ]
    )
    _patch_both_clients(monkeypatch, factory)
    captured = _capture_hooks()

    config = _load_demo_l1(tmp_path)
    result = _run(pipeline_runner.run_level_1(config, "go", crew_home=tmp_path))

    plan = json.loads(result.plan_path.read_text())
    assert len(plan["attempts"]) == 1
    assert plan["escalated"] is True
    # Both on-eval-fail (the verdict was non-pass) and on-escalate (status==escalate)
    # fire — the loop never retries because escalate is a hard signal.
    assert len(captured["on-eval-fail"]) == 1
    assert len(captured["on-escalate"]) == 1


def test_run_level_1_plan_contains_attempts_array(
    monkeypatch, tmp_path: Path
) -> None:
    factory = make_fake_copilot_client(
        replies=["## Summary\nok\n", _PASS_VERDICT]
    )
    _patch_both_clients(monkeypatch, factory)

    config = _load_demo_l1(tmp_path)
    result = _run(pipeline_runner.run_level_1(config, "go", crew_home=tmp_path))

    plan = json.loads(result.plan_path.read_text())
    assert "attempts" in plan
    assert isinstance(plan["attempts"], list)
    attempt = plan["attempts"][0]
    for key in ("attempt", "output_path", "started_at", "finished_at", "verdict"):
        assert key in attempt
    for key in ("status", "summary", "issues"):
        assert key in attempt["verdict"]


def test_run_pipeline_dispatches_level_0(monkeypatch, tmp_path: Path) -> None:
    factory = make_fake_copilot_client(reply="hi")
    monkeypatch.setattr(pipeline_runner, "CopilotClient", factory)

    config = pipeline_registry.load_pipeline(
        "demo", pipelines_dir=FIXTURES_PIPELINES, repo_root=tmp_path
    )
    result = _run(
        pipeline_runner.run_pipeline(config, "hello", crew_home=tmp_path)
    )
    assert result.output_path.exists()
    plan = json.loads(result.plan_path.read_text())
    # Level 0 plan has output_path (single), not attempts.
    assert "attempts" not in plan
    assert plan["level"] == 0


def test_run_pipeline_dispatches_level_1(monkeypatch, tmp_path: Path) -> None:
    factory = make_fake_copilot_client(
        replies=["## Summary\nok\n", _PASS_VERDICT]
    )
    _patch_both_clients(monkeypatch, factory)

    config = _load_demo_l1(tmp_path)
    result = _run(
        pipeline_runner.run_pipeline(config, "go", crew_home=tmp_path)
    )
    plan = json.loads(result.plan_path.read_text())
    assert plan["level"] == 1
    assert "attempts" in plan


def test_run_pipeline_rejects_level_2(tmp_path: Path) -> None:
    config = pipeline_registry.load_pipeline(
        "demo", pipelines_dir=FIXTURES_PIPELINES, repo_root=tmp_path
    )
    from dataclasses import replace

    level2 = replace(config, level=2)
    with pytest.raises(ValueError, match="Level 2 not supported"):
        _run(pipeline_runner.run_pipeline(level2, "x", crew_home=tmp_path))
