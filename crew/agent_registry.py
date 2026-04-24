"""Discover and load standalone / subagent markdown files.

Agents live at ``agents/*.md`` (flat, one file per agent) — sibling to
``pipelines/``. Each file is a single self-contained agent definition with
YAML frontmatter and a markdown body, same schema as pipeline generators.

Frontmatter fields (all optional unless marked):

* ``name`` (required) — agent identifier; used by the router and ``--agent``
* ``description`` — one-line summary fed to the router
* ``model`` — default model for this agent
* ``allowed-tools`` — list of tool identifiers (read / write / shell / mcp)
* ``standalone`` (bool, default ``true``) — include in the router's
  candidate list for auto-summon via a user prompt
* ``subagent`` (mapping, default absent) — enables pipeline generators to
  spawn this agent via the Copilot SDK's ``custom_agents``. See
  ``agent_registry.AgentConfig.subagent_infer``. (Day 3 wires the spawn
  path; Day 2.5 only parses the field.)

Resolution order for ``agents_dir``:
    1. explicit ``agents_dir`` argument
    2. ``CREW_AGENTS_DIR`` env var (overrides default; also used by Day 1
       harness state.py — same env var semantics)
    3. ``<cwd>/agents``
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from crew.harness.agent_loader import load_agent_md

_log = logging.getLogger("crew.agent_registry")


class AgentNotFound(KeyError):
    """Raised by ``load_agent`` when no matching agent file exists."""


@dataclass(frozen=True)
class AgentInfo:
    name: str
    description: str
    standalone: bool
    subagent_enabled: bool
    path: Path


@dataclass(frozen=True)
class AgentConfig:
    name: str
    description: str
    prompt: str
    model: str | None
    allowed_tools: list[str]
    frontmatter: dict
    path: Path
    standalone: bool
    subagent_enabled: bool
    subagent_infer: bool
    raw: dict = field(default_factory=dict)


def _resolve_agents_dir(agents_dir: Path | None) -> Path:
    if agents_dir is not None:
        return Path(agents_dir)
    env = os.environ.get("CREW_AGENTS_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "agents"


def _parse_entry(path: Path) -> tuple[AgentInfo, AgentConfig] | None:
    try:
        frontmatter, body = load_agent_md(path)
    except Exception as exc:
        _log.warning("skipping %s: %s", path, exc)
        return None

    name = frontmatter.get("name") or path.stem
    if not isinstance(name, str) or not name:
        _log.warning("skipping %s: missing/invalid name", path)
        return None

    description = str(frontmatter.get("description", "")).strip()
    standalone = bool(frontmatter.get("standalone", True))
    subagent_block = frontmatter.get("subagent")
    subagent_enabled = isinstance(subagent_block, dict)
    subagent_infer = (
        bool(subagent_block.get("infer", False)) if subagent_enabled else False
    )
    model_field = frontmatter.get("model")
    model: str | None = model_field if isinstance(model_field, str) else None
    allowed_tools = list(frontmatter.get("allowed-tools", []) or [])

    info = AgentInfo(
        name=name,
        description=description,
        standalone=standalone,
        subagent_enabled=subagent_enabled,
        path=path,
    )
    config = AgentConfig(
        name=name,
        description=description,
        prompt=body,
        model=model,
        allowed_tools=allowed_tools,
        frontmatter=frontmatter,
        path=path,
        standalone=standalone,
        subagent_enabled=subagent_enabled,
        subagent_infer=subagent_infer,
        raw=frontmatter,
    )
    return info, config


def discover(agents_dir: Path | None = None) -> list[AgentInfo]:
    """Return all parseable agent definitions under ``agents_dir``.

    Files whose frontmatter fails to parse log a warning and are skipped —
    discovery must not crash the CLI at startup.
    """
    base = _resolve_agents_dir(agents_dir)
    if not base.exists():
        return []
    out: list[AgentInfo] = []
    for path in sorted(base.glob("*.md")):
        parsed = _parse_entry(path)
        if parsed is None:
            continue
        out.append(parsed[0])
    return out


def discover_standalone(agents_dir: Path | None = None) -> list[AgentInfo]:
    """Return only the agents the intent router may auto-summon."""
    return [a for a in discover(agents_dir) if a.standalone]


def load_agent(name: str, *, agents_dir: Path | None = None) -> AgentConfig:
    base = _resolve_agents_dir(agents_dir)
    for path in sorted(base.glob("*.md")):
        parsed = _parse_entry(path)
        if parsed is None:
            continue
        info, config = parsed
        if info.name == name:
            return config
    raise AgentNotFound(name)
