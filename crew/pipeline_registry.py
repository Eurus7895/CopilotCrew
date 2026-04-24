"""Discover and load pipelines from the `pipelines/` directory.

Per CLAUDE.md "Architecture / 6. Pipelines are self-contained directories":
each pipeline lives at `pipelines/{name}/` with `pipeline.yaml`,
`agents/generator.md`, and optional `skills/`, `schemas/`, `README.md`.

This module exposes two views:

* ``PipelineInfo`` — cheap (name, description, level, path) for the intent
  router's prompt.
* ``PipelineConfig`` — fully resolved (agent frontmatter + prompt body,
  filtered MCP servers) for the runner.

`pipelines_dir` resolution order:
    1. explicit argument
    2. ``CREW_PIPELINES_DIR`` env var
    3. ``<cwd>/pipelines``
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from crew.harness.agent_loader import load_agent_md
from crew.sdk.mcp import load_global_mcp

_log = logging.getLogger("crew.pipeline_registry")


class PipelineNotFound(KeyError):
    """Raised by ``load_pipeline`` when no matching pipeline directory exists."""


@dataclass(frozen=True)
class PipelineInfo:
    name: str
    description: str
    level: int
    path: Path


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    level: int
    description: str
    agent_path: Path
    agent_frontmatter: dict
    agent_prompt: str
    mcp_servers: dict[str, Any]
    allowed_tools: list[str]
    output_subdir: str
    path: Path
    evaluator_path: Path | None = None
    evaluator_frontmatter: dict | None = None
    evaluator_prompt: str | None = None
    schema_path: Path | None = None
    schema_text: str | None = None
    raw: dict = field(default_factory=dict)


def _resolve_pipelines_dir(pipelines_dir: Path | None) -> Path:
    if pipelines_dir is not None:
        return Path(pipelines_dir)
    env = os.environ.get("CREW_PIPELINES_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "pipelines"


def _read_pipeline_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping, got {type(data).__name__}")
    return data


def discover(pipelines_dir: Path | None = None) -> list[PipelineInfo]:
    """Return a sorted list of pipelines discovered under ``pipelines_dir``.

    Subdirectories without a ``pipeline.yaml`` are skipped silently; malformed
    ``pipeline.yaml`` files log a warning and are skipped (discovery must not
    crash the CLI at startup).
    """
    base = _resolve_pipelines_dir(pipelines_dir)
    if not base.exists():
        return []

    out: list[PipelineInfo] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        yaml_path = entry / "pipeline.yaml"
        if not yaml_path.exists():
            continue
        try:
            data = _read_pipeline_yaml(yaml_path)
        except Exception as exc:
            _log.warning("skipping %s: %s", yaml_path, exc)
            continue
        name = data.get("name") or entry.name
        description = str(data.get("description", "")).strip()
        level = int(data.get("level", 0))
        out.append(PipelineInfo(name=name, description=description, level=level, path=entry))
    return out


def load_pipeline(
    name: str,
    *,
    pipelines_dir: Path | None = None,
    repo_root: Path | None = None,
) -> PipelineConfig:
    """Load the full config for ``name``.

    MCP servers in the returned config come from the repo-root ``.mcp.json``
    filtered by the ``mcp`` list in ``pipeline.yaml``. A name declared in
    ``pipeline.yaml`` but missing from ``.mcp.json`` logs a warning and is
    dropped (the pipeline still runs — missing MCP is a graceful degradation
    concern, not a startup error).
    """
    base = _resolve_pipelines_dir(pipelines_dir)
    pipeline_dir = base / name
    yaml_path = pipeline_dir / "pipeline.yaml"
    if not yaml_path.exists():
        # Also try matching against the `name:` field inside each pipeline.yaml
        for entry in discover(base):
            if entry.name == name:
                pipeline_dir = entry.path
                yaml_path = pipeline_dir / "pipeline.yaml"
                break
        else:
            raise PipelineNotFound(name)

    data = _read_pipeline_yaml(yaml_path)
    resolved_name = data.get("name") or pipeline_dir.name

    agent_rel = data.get("agent") or "agents/generator.md"
    agent_path = pipeline_dir / agent_rel
    if not agent_path.exists():
        raise FileNotFoundError(f"agent file missing: {agent_path}")
    frontmatter, prompt_body = load_agent_md(agent_path)

    declared_servers = list(data.get("mcp", []) or [])
    global_servers = load_global_mcp(repo_root)
    mcp_servers: dict[str, Any] = {}
    for key in declared_servers:
        if key in global_servers:
            mcp_servers[key] = global_servers[key]
        else:
            _log.warning(
                "pipeline %r declares MCP server %r which is absent from .mcp.json",
                resolved_name,
                key,
            )

    allowed_tools = list(data.get("allowed_tools", []) or [])
    output_subdir = str(data.get("output_subdir") or resolved_name)
    description = str(data.get("description", "")).strip()
    level = int(data.get("level", 0))

    evaluator_rel = data.get("evaluator") or "agents/evaluator.md"
    evaluator_path = pipeline_dir / evaluator_rel
    evaluator_frontmatter: dict | None = None
    evaluator_prompt: str | None = None
    if evaluator_path.exists():
        evaluator_frontmatter, evaluator_prompt = load_agent_md(evaluator_path)
    else:
        if level >= 1:
            raise FileNotFoundError(
                f"evaluator file missing for Level {level} pipeline: {evaluator_path}"
            )
        evaluator_path = None

    schema_rel = data.get("schema")
    schema_path: Path | None = None
    schema_text: str | None = None
    if schema_rel:
        candidate = pipeline_dir / schema_rel
        if not candidate.exists():
            raise FileNotFoundError(f"schema file missing: {candidate}")
        schema_path = candidate
        schema_text = candidate.read_text(encoding="utf-8")

    return PipelineConfig(
        name=resolved_name,
        level=level,
        description=description,
        agent_path=agent_path,
        agent_frontmatter=frontmatter,
        agent_prompt=prompt_body,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        output_subdir=output_subdir,
        path=pipeline_dir,
        evaluator_path=evaluator_path,
        evaluator_frontmatter=evaluator_frontmatter,
        evaluator_prompt=evaluator_prompt,
        schema_path=schema_path,
        schema_text=schema_text,
        raw=data,
    )
