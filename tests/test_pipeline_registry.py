import shutil
from pathlib import Path

import pytest

from crew import pipeline_registry
from crew.pipeline_registry import PipelineNotFound

FIXTURES_PIPELINES = Path(__file__).parent / "fixtures" / "pipelines"


def test_discover_returns_demo_pipeline() -> None:
    infos = pipeline_registry.discover(FIXTURES_PIPELINES)
    names = sorted(info.name for info in infos)
    assert names == ["demo", "demo-l1"]
    by_name = {i.name: i for i in infos}
    assert by_name["demo"].level == 0
    assert "Fixture pipeline" in by_name["demo"].description
    assert by_name["demo-l1"].level == 1


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


def test_level_0_pipeline_has_no_evaluator() -> None:
    config = pipeline_registry.load_pipeline(
        "demo", pipelines_dir=FIXTURES_PIPELINES
    )
    # Level 0 pipelines silently omit the evaluator when missing.
    assert config.evaluator_path is None
    assert config.evaluator_prompt is None
    assert config.schema_text is None


def test_load_demo_l1_surfaces_evaluator_and_schema() -> None:
    config = pipeline_registry.load_pipeline(
        "demo-l1", pipelines_dir=FIXTURES_PIPELINES
    )
    assert config.level == 1
    assert config.evaluator_path is not None
    assert config.evaluator_prompt is not None
    assert "JSON" in config.evaluator_prompt
    assert config.schema_path is not None
    assert config.schema_text is not None
    assert "Summary" in config.schema_text


def test_load_level1_missing_evaluator_raises(tmp_path: Path) -> None:
    src = FIXTURES_PIPELINES / "demo-l1"
    dst_root = tmp_path / "pipelines"
    dst = dst_root / "demo-l1"
    shutil.copytree(src, dst)
    (dst / "agents" / "evaluator.md").unlink()

    with pytest.raises(FileNotFoundError, match="evaluator file missing"):
        pipeline_registry.load_pipeline("demo-l1", pipelines_dir=dst_root)


def test_load_pipeline_missing_schema_file_raises(tmp_path: Path) -> None:
    src = FIXTURES_PIPELINES / "demo-l1"
    dst_root = tmp_path / "pipelines"
    dst = dst_root / "demo-l1"
    shutil.copytree(src, dst)
    (dst / "schemas" / "output.json").unlink()

    with pytest.raises(FileNotFoundError, match="schema file missing"):
        pipeline_registry.load_pipeline("demo-l1", pipelines_dir=dst_root)


# ── v1 pipeline-set regression (Day 4-B) ─────────────────────────────────────


REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_PIPELINES_DIR = REPO_ROOT / "pipelines"

V1_PIPELINES: dict[str, int] = {
    "daily-standup": 0,
    "release-notes": 0,
    "incident-triage": 1,
    "ticket-refinement": 1,
    "code-review-routing": 1,
}


def test_v1_pipelines_all_discoverable() -> None:
    """All five v1 pipelines (CLAUDE.md "Build Order") must be present
    and at the right level. Catches accidental drops or misconfiguration.
    """
    infos = pipeline_registry.discover(REAL_PIPELINES_DIR)
    by_name = {i.name: i for i in infos}
    for name, expected_level in V1_PIPELINES.items():
        assert name in by_name, f"v1 pipeline {name!r} missing from pipelines/"
        assert by_name[name].level == expected_level, (
            f"{name}: expected level {expected_level}, got {by_name[name].level}"
        )


def test_v1_pipelines_all_load_cleanly() -> None:
    """Each v1 pipeline must fully resolve: agent prompt, evaluator (Level
    1), schema (Level 1), and at least one MCP server declaration.
    """
    for name, expected_level in V1_PIPELINES.items():
        cfg = pipeline_registry.load_pipeline(
            name, pipelines_dir=REAL_PIPELINES_DIR, repo_root=REPO_ROOT
        )
        assert cfg.agent_prompt.strip(), f"{name}: empty agent prompt"
        assert cfg.mcp_servers, f"{name}: no MCP servers loaded"
        if expected_level >= 1:
            assert cfg.evaluator_prompt, f"{name}: Level 1 missing evaluator prompt"
            assert cfg.schema_text, f"{name}: Level 1 missing schema text"
        else:
            assert cfg.evaluator_prompt is None, (
                f"{name}: Level 0 unexpectedly has an evaluator"
            )
