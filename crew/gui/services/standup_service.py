"""Bridge to the ``daily-standup`` pipeline + latest-output reader."""

from __future__ import annotations

import asyncio
import contextlib
import io
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
    """Run the daily-standup pipeline with stdout redirected into the SSE bus.

    Concurrency: guarded by a module-level lock. Raises ``AlreadyRunning``
    if a run is already in flight.
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

        sink = _QueueSink(pipeline_name=_PIPELINE_NAME)
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

        try:
            with contextlib.redirect_stdout(sink):
                await pipeline_runner.run_pipeline(
                    config,
                    "Generate today's standup from recent GitHub activity.",
                    model=cfg.model,
                    crew_home=cfg.crew_home,
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
        finally:
            await sink.flush_remaining()

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


class _QueueSink(io.TextIOBase):
    """Write-side sink for ``contextlib.redirect_stdout``.

    Buffers partial lines and fans complete lines out as
    ``pipeline_progress`` SSE events. Safe to call from non-async code —
    publish is scheduled onto the running event loop.
    """

    def __init__(self, *, pipeline_name: str) -> None:
        super().__init__()
        self._pipeline = pipeline_name
        self._buf = ""
        self._loop = asyncio.get_event_loop()

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:  # type: ignore[override]
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, _, self._buf = self._buf.partition("\n")
            self._dispatch(line)
        return len(s)

    async def flush_remaining(self) -> None:
        if self._buf:
            tail, self._buf = self._buf, ""
            await publish(
                "pipeline_progress",
                {"pipeline": self._pipeline, "state": "delta", "delta": tail},
            )

    def _dispatch(self, line: str) -> None:
        coro = publish(
            "pipeline_progress",
            {"pipeline": self._pipeline, "state": "delta", "delta": line + "\n"},
        )
        try:
            asyncio.ensure_future(coro, loop=self._loop)
        except RuntimeError:
            # Event loop closed — drop silently; run_generate's finally
            # will re-raise the real cause.
            pass
