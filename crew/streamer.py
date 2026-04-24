"""Central Copilot SDK event → sink strategies.

Per CLAUDE.md Day 4-B: "streamer.py: terminal output + summary mode".
Before this module, ``crew.direct`` and ``crew.pipeline_runner`` each had
their own inline ``on_event`` callback that hard-coded writing to stdout
and buffering. The GUI had to hack around that with
``contextlib.redirect_stdout``. This module extracts the strategy so
callers pick how deltas are surfaced and share one implementation of
"which SDK event types do we care about".

Three strategies ship:

* :class:`TerminalStreamer` — the legacy behaviour: write deltas to
  stdout as they arrive, buffer them for the return value.
* :class:`SummaryStreamer` — collect deltas silently. Used by the
  GUI's ``/chat`` handler and by callers that want the full text only
  after the SDK turn completes (tests, CI).
* :class:`CallbackStreamer` — fan each delta out to an injected
  function; ``SummaryStreamer`` is the no-op case of this.

The base class also surfaces ``TOOL_EXECUTION_{START,COMPLETE}`` via
``on_tool_use`` hooks so pipeline_runner can continue firing
``pre-tool-use`` / ``post-tool-use`` in exactly one place.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from copilot.generated.session_events import SessionEvent, SessionEventType

_TOOL_USE_START = getattr(SessionEventType, "TOOL_EXECUTION_START", None)
_TOOL_USE_END = getattr(SessionEventType, "TOOL_EXECUTION_COMPLETE", None)


class Streamer:
    """Base: accumulate deltas; subclasses decide whether to surface them.

    ``on_tool_use`` defaults to a no-op so simple callers (direct mode,
    chat) ignore tool events. The pipeline runner overrides it to fire
    the hook registry.
    """

    def __init__(self) -> None:
        self._buffer: list[str] = []

    def handle_event(self, event: SessionEvent) -> None:
        """The callback registered on a session. Dispatches by event type."""
        etype = event.type
        if etype == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                self._buffer.append(delta)
                self.on_delta(delta)
            return
        if _TOOL_USE_START is not None and etype == _TOOL_USE_START:
            self.on_tool_use("start", event)
            return
        if _TOOL_USE_END is not None and etype == _TOOL_USE_END:
            self.on_tool_use("end", event)
            return

    # ── subclass hooks ───────────────────────────────────────────────
    def on_delta(self, delta: str) -> None:  # noqa: B027 - intentionally empty
        """Called for each assistant-message delta. Default: no-op."""

    def on_tool_use(self, phase: str, event: SessionEvent) -> None:  # noqa: B027
        """Called on tool-execution events. ``phase`` is "start" or "end"."""

    # ── accessors ────────────────────────────────────────────────────
    @property
    def text(self) -> str:
        """Concatenated deltas, unstripped."""
        return "".join(self._buffer)

    def finish_line(self) -> None:
        """Hook for subclasses that need to emit a trailing newline."""


class TerminalStreamer(Streamer):
    """Write deltas to stdout as they arrive, buffer for return."""

    def on_delta(self, delta: str) -> None:
        sys.stdout.write(delta)
        sys.stdout.flush()

    def finish_line(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


class SummaryStreamer(Streamer):
    """Collect silently. Retrieve the text via ``.text`` when done."""


class CallbackStreamer(Streamer):
    """Fan each delta to an external sink (GUI SSE, log, test spy)."""

    def __init__(
        self,
        on_delta_fn: Callable[[str], Any] | None = None,
        on_tool_use_fn: Callable[[str, SessionEvent], Any] | None = None,
    ) -> None:
        super().__init__()
        self._delta_fn = on_delta_fn
        self._tool_fn = on_tool_use_fn

    def on_delta(self, delta: str) -> None:
        if self._delta_fn is not None:
            self._delta_fn(delta)

    def on_tool_use(self, phase: str, event: SessionEvent) -> None:
        if self._tool_fn is not None:
            self._tool_fn(phase, event)


__all__ = [
    "Streamer",
    "TerminalStreamer",
    "SummaryStreamer",
    "CallbackStreamer",
]
