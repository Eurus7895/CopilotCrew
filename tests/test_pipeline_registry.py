from pathlib import Path

import pytest

from crew import pipeline_registry
from crew.pipeline_registry import PipelineNotFound

FIXTURES_PIPELINES = Path(__file__).parent / "fixtures" / "pipelines"


def test_discover_returns_demo_pipeline() -> None:
    infos = pipeline_registry.discover(FIXTURES_PIPELINES)
    names = [info.name for info in infos]
    assert names == ["demo"]
    assert infos[0].level == 0
    assert "Fixture pipeline" in infos[0].description


def test_discover_skips_subdir_without_pipeline_yaml(tmp_path: Path) -> None:
    (tmp_path / "loose_dir").mkdir()
    (tmp_path / "ghost").mkdir()
    # Also copy the demo fixture so we have one valid entry to prove it doesn't skip everything.
    valid = tmp_path / "demo"
    valid.mkdir()
    (valid / "pipeline.yaml").write_text(
        "name: demo\ndescription: x\nlevel: 0\nagent: agents/g.md\n"
    )
    (valid / "agents").mkdir()
    (valid / "agents" / "g.md").write_text("---\n---\nbody\n")

    infos = pipeline_registry.discover(tmp_path)
    assert [i.name for i in infos] == ["demo"]


def test_discover_skips_malformed_yaml(tmp_path: Path, caplog) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "pipeline.yaml").write_text("this is :: not valid yaml :::")
    # Actually that may parse as a string. Use an explicit non-mapping:
    (bad / "pipeline.yaml").write_text("- just\n- a\n- list\n")

    infos = pipeline_registry.discover(tmp_path)
    assert infos == []


def test_load_pipeline_fills_frontmatter_and_prompt(tmp_path: Path) -> None:
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(
        '{"mcpServers": {"github": {"type": "http", "url": "https://example/mcp"}}}'
    )

    config = pipeline_registry.load_pipeline(
        "demo",
        pipelines_dir=FIXTURES_PIPELINES,
        repo_root=tmp_path,
    )
    assert config.name == "demo"
    assert config.level == 0
    assert config.agent_frontmatter["name"] == "demo-generator"
    assert config.agent_prompt.startswith("You are a demo generator")
    assert config.mcp_servers == {
        "github": {"type": "http", "url": "https://example/mcp"}
    }
    # Declared-but-missing server is dropped, not errored.
    assert "nonexistent" not in config.mcp_servers
    assert config.output_subdir == "demo-out"
    assert config.allowed_tools == ["read"]


def test_load_pipeline_unknown_raises() -> None:
    with pytest.raises(PipelineNotFound):
        pipeline_registry.load_pipeline("does-not-exist", pipelines_dir=FIXTURES_PIPELINES)


def test_load_pipeline_resolves_repo_root_for_mcp(tmp_path: Path) -> None:
    # No .mcp.json under repo_root → mcp_servers is empty, no crash.
    config = pipeline_registry.load_pipeline(
        "demo",
        pipelines_dir=FIXTURES_PIPELINES,
        repo_root=tmp_path,
    )
    assert config.mcp_servers == {}
