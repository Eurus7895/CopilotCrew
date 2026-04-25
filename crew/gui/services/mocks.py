"""Readers for the JSONL-backed stub data sources.

Each loader returns ``[]`` if the file is missing — templates render a
muted empty state so missing data never breaks the UI. Future hooks /
pipelines can append to these files without touching GUI code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crew.gui.config import GUIConfig


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def load_timeline(cfg: GUIConfig) -> list[dict[str, Any]]:
    return _load_jsonl(cfg.gui_dir / "timeline.jsonl")


def load_timeline_event(cfg: GUIConfig, event_id: str) -> dict[str, Any] | None:
    for row in load_timeline(cfg):
        if str(row.get("id")) == event_id:
            return row
    return None


def load_pr_activity(cfg: GUIConfig) -> list[dict[str, Any]]:
    return _load_jsonl(cfg.gui_dir / "pr_activity.jsonl")


def load_slack_mentions(cfg: GUIConfig) -> list[dict[str, Any]]:
    return _load_jsonl(cfg.gui_dir / "slack_mentions.jsonl")


def load_working_on(cfg: GUIConfig) -> list[dict[str, Any]]:
    return _load_jsonl(cfg.gui_dir / "working_on.jsonl")


def load_facts(cfg: GUIConfig) -> list[dict[str, Any]]:
    return _load_jsonl(cfg.memory_path)
