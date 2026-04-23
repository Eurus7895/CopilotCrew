"""Status-bar data: online probe + model label."""

from __future__ import annotations

from dataclasses import dataclass

from crew.gui.config import GUIConfig


@dataclass(frozen=True)
class Status:
    online: bool
    model: str


def probe(cfg: GUIConfig) -> Status:
    """Return the status line data.

    V1: always reports ``online=True`` — the FastAPI process itself is
    running, so from the user's perspective Crew is up. A real SDK
    reachability probe is deferred until the Copilot client exposes a
    cheap ping (we do not want to spend tokens on a dashboard refresh).
    """
    model = cfg.model or "gpt-4.1"
    return Status(online=True, model=model)
