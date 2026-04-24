"""Loaders for `.mcp.json` config.

The Copilot SDK can auto-discover `.mcp.json` from the working directory when
`enable_config_discovery=True` is passed to `create_session`. Direct mode uses
that path. This module exists for explicit loading (tests, future
pipeline-specific configs that override the global one).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_global_mcp(repo_root: Path | str | None = None) -> dict[str, Any]:
    """Read `.mcp.json` from `repo_root` (defaults to cwd) and return the
    `mcpServers` mapping. Returns an empty dict if the file is missing.
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    path = root / ".mcp.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("mcpServers", {})
