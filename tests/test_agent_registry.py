from pathlib import Path

import pytest

from crew import agent_registry
from crew.agent_registry import AgentNotFound

FIXTURES = Path(__file__).parent / "fixtures" / "agents"


def test_discover_returns_all_parseable_agents() -> None:
    infos = agent_registry.discover(FIXTURES)
    names = {info.name for info in infos}
    assert names == {"demo-coder", "subagent-only"}


def test_discover_standalone_filters_out_subagent_only() -> None:
    infos = agent_registry.discover_standalone(FIXTURES)
    names = [i.name for i in infos]
    assert names == ["demo-coder"]


def test_load_agent_returns_prompt_and_frontmatter() -> None:
    config = agent_registry.load_agent("demo-coder", agents_dir=FIXTURES)
    assert config.name == "demo-coder"
    assert config.description.startswith("Demo coding agent")
    assert config.prompt.startswith("You are a demo coder")
    assert config.model == "gpt-4.1"
    assert config.allowed_tools == ["read", "write"]
    assert config.standalone is True
    assert config.subagent_enabled is True
    assert config.subagent_infer is False


def test_load_agent_unknown_raises() -> None:
    with pytest.raises(AgentNotFound):
        agent_registry.load_agent("nope", agents_dir=FIXTURES)


def test_subagent_only_agent_is_loadable_but_not_standalone() -> None:
    config = agent_registry.load_agent("subagent-only", agents_dir=FIXTURES)
    assert config.standalone is False
    assert config.subagent_enabled is True
    assert config.subagent_infer is True


def test_discover_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert agent_registry.discover(tmp_path / "does-not-exist") == []


def test_discover_skips_file_without_name(tmp_path: Path) -> None:
    (tmp_path / "anon.md").write_text("---\ndescription: x\n---\nbody\n")
    (tmp_path / "good.md").write_text("---\nname: good\n---\nbody\n")
    infos = agent_registry.discover(tmp_path)
    # The anonymous file falls back to the file stem (`anon`).
    names = {i.name for i in infos}
    assert names == {"anon", "good"}


def test_env_var_resolves_agents_dir(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "env.md").write_text("---\nname: env-agent\n---\nbody\n")
    monkeypatch.setenv("CREW_AGENTS_DIR", str(tmp_path))
    infos = agent_registry.discover()
    assert [i.name for i in infos] == ["env-agent"]
