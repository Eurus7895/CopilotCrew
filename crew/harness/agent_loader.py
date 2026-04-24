"""Parse agent.md files (YAML frontmatter + markdown body).

Per CLAUDE.md "Architecture / 1. Agents": the agent definition IS the prompt.
The frontmatter is configuration; the markdown body is the system prompt.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_DELIMITER = "---"


def load_agent_md(path: str | Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_markdown).

    Files without a leading `---` block return `({}, full_text)`.
    """
    text = Path(path).read_text()
    lines = text.splitlines(keepends=True)

    if not lines or lines[0].strip() != _DELIMITER:
        return {}, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIMITER:
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    frontmatter_text = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :]).lstrip("\n")

    frontmatter = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}

    return frontmatter, body
