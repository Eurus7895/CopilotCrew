"""Bridge to the ``daily-standup`` pipeline + latest-output reader."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from crew.gui.config import GUIConfig
from crew.gui.services.events_bus import publish

_log = logging.getLogger("crew.gui.standup_service")

_PIPELINE_NAME = "daily-standup"
_run_lock = asyncio.Lock()


@dataclass(frozen=True)
class Draft:
    body: str | None
    path: Path | None


class AlreadyRunning(RuntimeError):
    """Raised when a second regeneration is requested while one is in flight."""


def _standup_outputs_dir(cfg: GUIConfig) -> Path:
    return cfg.outputs_dir / "daily-standup"


def latest_draft(cfg: GUIConfig) -> Draft:
    out_dir = _standup_outputs_dir(cfg)
    if not out_dir.exists():
        return Draft(body=None, path=None)
    files = sorted(
        (p for p in out_dir.glob("*.md") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return Draft(body=None, path=None)
    newest = files[0]
    try:
        body = newest.read_text(encoding="utf-8")
    except OSError:
        return Draft(body=None, path=newest)
    return Draft(body=body.strip(), path=newest)


def delete_latest(cfg: GUIConfig) -> Path | None:
    draft = latest_draft(cfg)
    if draft.path is None:
        return None
    try:
        draft.path.unlink()
    except OSError:
        return None
    return draft.path


def is_running() -> bool:
    return _run_lock.locked()


async def run_generate(cfg: GUIConfig) -> None:
    """Run the daily-standup pipeline; stream deltas onto the SSE bus.

    Concurrency: guarded by a module-level lock. Raises ``AlreadyRunning``
    if a run is already in flight. Uses a ``CallbackStreamer`` to publish
    each assistant-message delta as a ``pipeline_progress`` event — the
    ``#standup-progress`` strip in every theme listens for these.
    """
    if _run_lock.locked():
        raise AlreadyRunning("daily-standup pipeline already running")

    async with _run_lock:
        await publish("pipeline_progress", {"pipeline": _PIPELINE_NAME, "state": "starting"})

        # Lazy imports — the Copilot SDK is heavy and may be unavailable
        # in environments that only need the read-only viewer. Failure
        # here is reported on the SSE bus, not at GUI boot.
        try:
            from crew import pipeline_registry, pipeline_runner
            from crew.streamer import CallbackStreamer
        except ImportError as exc:
            await publish(
                "pipeline_progress",
                {
                    "pipeline": _PIPELINE_NAME,
                    "state": "error",
                    "detail": f"copilot SDK not installed: {exc}",
                },
            )
            return

        try:
            config = pipeline_registry.load_pipeline(_PIPELINE_NAME)
        except Exception as exc:
            _log.exception("failed to load pipeline %r", _PIPELINE_NAME)
            await publish(
                "pipeline_progress",
                {
                    "pipeline": _PIPELINE_NAME,
                    "state": "error",
                    "detail": f"load_pipeline: {exc}",
                },
            )
            return

        loop = asyncio.get_event_loop()

        def _on_delta(delta: str) -> None:
            coro = publish(
                "pipeline_progress",
                {"pipeline": _PIPELINE_NAME, "state": "delta", "delta": delta},
            )
            try:
                asyncio.ensure_future(coro, loop=loop)
            except RuntimeError:
                pass  # loop closed — drop

        streamer = CallbackStreamer(on_delta_fn=_on_delta)

        try:
            await pipeline_runner.run_pipeline(
                config,
                "Generate today's standup from recent GitHub activity.",
                model=cfg.model,
                crew_home=cfg.crew_home,
                streamer=streamer,
            )
        except Exception as exc:
            _log.exception("daily-standup pipeline failed")
            await publish(
                "pipeline_progress",
                {
                    "pipeline": _PIPELINE_NAME,
                    "state": "error",
                    "detail": str(exc),
                },
            )
            return

        draft = latest_draft(cfg)
        await publish(
            "pipeline_progress",
            {"pipeline": _PIPELINE_NAME, "state": "done"},
        )
        if draft.path is not None:
            await publish(
                "output_updated",
                {
                    "pipeline": _PIPELINE_NAME,
                    "path": str(draft.path),
                },
            )
