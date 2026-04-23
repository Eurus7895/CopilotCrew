"""Discover and load skills from ``skills/<name>/SKILL.md``.

Skills are task-specific capability bundles (Claude-Code style): a markdown
file with instructions + optional ``scripts/`` and ``references/``
directories. Slash commands invoke a skill; the skill's instructions are
appended to the session's system message so the active agent gains the
capability in-context.

Skills differ from agents:

* Agents = *who is answering* (persona swap, replaces system prompt)
* Skills = *what task is being done* (capability injection, appends to
  system prompt)

Layout:
    skills/
        debug/
            SKILL.md            ← instructions; frontmatter + markdown body
            references/         ← optional; read-only reference files
                patterns.md
            scripts/            ← optional; referenced by the skill body
                bisect.sh

``skills_dirs`` resolution order for discovery:
    1. explicit list of search roots
    2. ``CREW_SKILLS_DIR`` env var (single root — same semantics as the
       dormant v1 env var in ``crew/harness/skill_loader.py``)
    3. ``[<cwd>/skills]``

Plugins (Phase 2+, not implemented yet) will contribute additional search
roots like ``<cwd>/plugins/<plugin-name>/skills`` without changing the
file format.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from crew.harness.agent_loader import load_agent_md

_log = logging.getLogger("crew.skill_registry")


class SkillNotFound(KeyError):
    """Raised by ``load_skill`` when no matching skill directory exists."""


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    version: str
    path: Path


@dataclass(frozen=True)
class SkillConfig:
    name: str
    description: str
    version: str
    instructions: str           # markdown body appended to system message
    allowed_tools: list[str]
    frontmatter: dict
    path: Path                  # the SKILL.md file
    dir: Path                   # skills/<name>/
    references_dir: Path | None
    scripts_dir: Path | None
    raw: dict = field(default_factory=dict)


def _resolve_skills_dirs(skills_dirs: list[Path] | Path | None) -> list[Path]:
    if skills_dirs is not None:
        if isinstance(skills_dirs, Path):
            return [skills_dirs]
        return [Path(p) for p in skills_dirs]
    env = os.environ.get("CREW_SKILLS_DIR")
    if env:
        return [Path(env)]
    return [Path.cwd() / "skills"]


def _parse_skill_dir(skill_dir: Path) -> tuple[SkillInfo, SkillConfig] | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        frontmatter, body = load_agent_md(skill_md)
    except Exception as exc:
        _log.warning("skipping %s: %s", skill_md, exc)
        return None

    name = frontmatter.get("name") or skill_dir.name
    if not isinstance(name, str) or not name:
        _log.warning("skipping %s: missing/invalid name", skill_md)
        return None

    description = str(frontmatter.get("description", "")).strip()
    version = str(frontmatter.get("version", "0.0.0"))
    allowed_tools = list(frontmatter.get("allowed-tools", []) or [])

    references_dir = skill_dir / "references" if (skill_dir / "references").is_dir() else None
    scripts_dir = skill_dir / "scripts" if (skill_dir / "scripts").is_dir() else None

    info = SkillInfo(name=name, description=description, version=version, path=skill_dir)
    config = SkillConfig(
        name=name,
        description=description,
        version=version,
        instructions=body,
        allowed_tools=allowed_tools,
        frontmatter=frontmatter,
        path=skill_md,
        dir=skill_dir,
        references_dir=references_dir,
        scripts_dir=scripts_dir,
        raw=frontmatter,
    )
    return info, config


def discover(skills_dirs: list[Path] | Path | None = None) -> list[SkillInfo]:
    """Return all parseable skills under ``skills_dirs``.

    Skills with the same ``name`` in multiple search roots are kept both —
    duplicates log a warning but don't block discovery. Resolution (which
    one ``load_skill`` returns) is first-root-wins.
    """
    roots = _resolve_skills_dirs(skills_dirs)
    seen: dict[str, Path] = {}
    out: list[SkillInfo] = []
    for root in roots:
        if not root.exists():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            parsed = _parse_skill_dir(skill_md.parent)
            if parsed is None:
                continue
            info = parsed[0]
            if info.name in seen:
                _log.warning(
                    "skill %r at %s shadowed by earlier definition at %s",
                    info.name,
                    info.path,
                    seen[info.name],
                )
                continue
            seen[info.name] = info.path
            out.append(info)
    return out


def load_skill(name: str, *, skills_dirs: list[Path] | Path | None = None) -> SkillConfig:
    roots = _resolve_skills_dirs(skills_dirs)
    for root in roots:
        if not root.exists():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            parsed = _parse_skill_dir(skill_md.parent)
            if parsed is None:
                continue
            info, config = parsed
            if info.name == name:
                return config
    raise SkillNotFound(name)
