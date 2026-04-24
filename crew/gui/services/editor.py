"""Open a file in the user's ``$EDITOR``."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


def open_in_editor(path: Path) -> bool:
    """Launch ``$EDITOR`` on ``path``. Returns True on successful spawn."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        return False
    try:
        parts = shlex.split(editor) + [str(path)]
        subprocess.Popen(parts, stdin=None, stdout=None, stderr=None, close_fds=True)
    except (OSError, ValueError):
        return False
    return True
