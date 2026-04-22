from pathlib import Path

from crew.harness.agent_loader import load_agent_md

FIXTURE = Path(__file__).parent / "fixtures" / "sample_agent.md"


def test_frontmatter_parses_to_expected_dict():
    frontmatter, _ = load_agent_md(FIXTURE)
    assert frontmatter["name"] == "incident-generator"
    assert frontmatter["model"] == "gpt-4.1"
    assert frontmatter["maxTurns"] == 30
    assert frontmatter["disallowedTools"] == ["Write", "Edit"]


def test_body_starts_after_closing_delimiter():
    _, body = load_agent_md(FIXTURE)
    assert body.startswith("You are an incident response analyst.")
    # Nothing from the frontmatter leaked into the body.
    assert "name:" not in body.splitlines()[0]


def test_file_without_frontmatter(tmp_path: Path):
    p = tmp_path / "plain.md"
    p.write_text("just some markdown\n")
    frontmatter, body = load_agent_md(p)
    assert frontmatter == {}
    assert body == "just some markdown\n"


def test_file_with_unclosed_frontmatter(tmp_path: Path):
    p = tmp_path / "weird.md"
    p.write_text("---\nname: orphan\nno closer here\n")
    frontmatter, body = load_agent_md(p)
    assert frontmatter == {}
    assert body.startswith("---\n")
