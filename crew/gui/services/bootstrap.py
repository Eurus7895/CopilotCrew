"""First-run seeding of ``~/.crew/gui/`` stub data files."""

from __future__ import annotations

import shutil
from pathlib import Path


_GUI_DIR_FILES = {
    "timeline.jsonl",
    "pr_activity.jsonl",
    "slack_mentions.jsonl",
    "working_on.jsonl",
}


def seed_gui_dir(gui_dir: Path, seed_dir: Path) -> None:
    """Copy stub JSONL files into ``gui_dir`` for any missing entries.

    Never overwrites existing files — users are free to edit the JSONL by
    hand, and future hooks may append to them. Files destined for
    ``~/.crew/`` (memory.jsonl) are handled by ``seed_memory``.
    """
    gui_dir.mkdir(parents=True, exist_ok=True)
    if not seed_dir.exists():
        return
    for src in seed_dir.iterdir():
        if not src.is_file() or src.name not in _GUI_DIR_FILES:
            continue
        dst = gui_dir / src.name
        if dst.exists():
            continue
        shutil.copy2(src, dst)


def seed_memory(memory_path: Path, seed_file: Path) -> None:
    """Seed ``~/.crew/memory.jsonl`` if it does not exist."""
    if memory_path.exists() or not seed_file.exists():
        return
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_file, memory_path)
