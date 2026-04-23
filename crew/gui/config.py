"""GUI runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_crew_home() -> Path:
    env = os.environ.get("CREW_HOME")
    if env:
        return Path(env)
    return Path.home() / ".crew"


@dataclass(frozen=True)
class GUIConfig:
    crew_home: Path
    model: str | None
    user_name: str
    host: str
    port: int

    @property
    def gui_dir(self) -> Path:
        return self.crew_home / "gui"

    @property
    def memory_path(self) -> Path:
        return self.crew_home / "memory.jsonl"

    @property
    def outputs_dir(self) -> Path:
        return self.crew_home / "outputs"

    @classmethod
    def build(
        cls,
        *,
        crew_home: Path | None = None,
        model: str | None = None,
        user_name: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> "GUIConfig":
        home = Path(crew_home) if crew_home is not None else _default_crew_home()
        return cls(
            crew_home=home,
            model=model or os.environ.get("CREW_MODEL"),
            user_name=user_name or os.environ.get("CREW_USER") or "there",
            host=host,
            port=port,
        )
