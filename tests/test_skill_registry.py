from pathlib import Path

import pytest

from crew import skill_registry
from crew.skill_registry import SkillNotFound

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


def test_discover_returns_fixture_skill() -> None:
    infos = skill_registry.discover([FIXTURES])
    names = [i.name for i in infos]
    assert names == ["demo-debug"]
    assert infos[0].description.startswith("Fixture debugging skill")


def test_load_skill_returns_instructions_and_frontmatter() -> None:
    config = skill_registry.load_skill("demo-debug", skills_dirs=[FIXTURES])
    assert config.name == "demo-debug"
    assert config.version == "0.0.1"
    assert config.allowed_tools == ["read"]
    assert "systematic" in config.instructions.lower()
    assert config.references_dir is None
    assert config.scripts_dir is None


def test_load_skill_unknown_raises() -> None:
    with pytest.raises(SkillNotFound):
        skill_registry.load_skill("nope", skills_dirs=[FIXTURES])


def test_discover_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert skill_registry.discover([tmp_path / "does-not-exist"]) == []


def test_discover_skips_subdir_without_skill_md(tmp_path: Path) -> None:
    (tmp_path / "loose").mkdir()          # no SKILL.md
    ok = tmp_path / "good"
    ok.mkdir()
    (ok / "SKILL.md").write_text("---\nname: good\n---\nbody\n")
    infos = skill_registry.discover([tmp_path])
    assert [i.name for i in infos] == ["good"]


def test_references_and_scripts_dirs_are_detected(tmp_path: Path) -> None:
    skill = tmp_path / "rich"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: rich\n---\ninstructions\n")
    (skill / "references").mkdir()
    (skill / "scripts").mkdir()

    config = skill_registry.load_skill("rich", skills_dirs=[tmp_path])
    assert config.references_dir == skill / "references"
    assert config.scripts_dir == skill / "scripts"


def test_env_var_resolves_skills_dir(tmp_path: Path, monkeypatch) -> None:
    skill = tmp_path / "env-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: env-skill\n---\nbody\n")
    monkeypatch.setenv("CREW_SKILLS_DIR", str(tmp_path))
    infos = skill_registry.discover()
    assert [i.name for i in infos] == ["env-skill"]


def test_multiple_roots_first_wins(tmp_path: Path) -> None:
    # Two search roots, both define a skill called `shared`.
    # Discovery should keep only the first and warn.
    a = tmp_path / "a" / "shared"
    a.mkdir(parents=True)
    (a / "SKILL.md").write_text("---\nname: shared\ndescription: first\n---\nfirst\n")
    b = tmp_path / "b" / "shared"
    b.mkdir(parents=True)
    (b / "SKILL.md").write_text("---\nname: shared\ndescription: second\n---\nsecond\n")

    infos = skill_registry.discover([tmp_path / "a", tmp_path / "b"])
    assert [i.name for i in infos] == ["shared"]
    assert infos[0].description == "first"

    # And load_skill returns the first root's version too.
    config = skill_registry.load_skill(
        "shared", skills_dirs=[tmp_path / "a", tmp_path / "b"]
    )
    assert config.instructions.strip() == "first"
