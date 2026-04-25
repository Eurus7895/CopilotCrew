"""Centralized streaming layer for Crew's Copilot SDK sessions.

Every Copilot session in Crew wires the same basic ``on_event`` handler:
capture ``ASSISTANT_MESSAGE_DELTA`` tokens into a buffer, optionally echo
them to stdout, and optionally surface tool-execution events to the hook
registry. Direct mode, the pipeline runner, the evaluator, and the intent
router each re-implemented this handler with subtle variations. This
module is the single place that implementation lives.

Three modes:

* ``verbose`` — every assistant token is streamed to stdout as it
  arrives. Default for direct / agent / slash modes. Output ends with a
  trailing newline so subsequent prompts don't stack on the last line.
* ``summary`` — terse status lines only. Suitable for pipelines invoked
  non-interactively (cron, CI, log files) where a 400-word report
  streaming token-by-token just creates noise. One line per phase:
  generator start, each tool call, generator done with char count. The
  full assistant text is still captured and written to the output file
  per the pipeline's audit trail — ``summary`` only changes what lands
  on the user's terminal.
* ``silent`` — capture-only, no stdout output. Used by the evaluator and
  the intent router, both of which collect a structured reply they parse
  downstream.

Usage::

    streamer = Streamer(mode="verbose")
    session.on(streamer.handler)
    await session.send_and_wait(prompt)
    text = streamer.finish()

``finish()`` is idempotent and returns the accumulated assistant text.
Callers that only need the text (not the trailing-newline side effect)
may read ``streamer.text`` directly.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, TextIO

from copilot.generated.session_events import SessionEvent, SessionEventType

StreamMode = Literal["verbose", "summary", "silent"]

ToolEventCb = Callable[[SessionEvent], None]

# The installed Copilot SDK may not expose tool-execution events. Resolve
# the enum members once at import time and treat their absence as a
# feature gap — downstream hooks and summary-mode tool lines degrade
# silently rather than raising.
_TOOL_USE_START = getattr(SessionEventType, "TOOL_EXECUTION_START", None)
_TOOL_USE_END = getattr(SessionEventType, "TOOL_EXECUTION_COMPLETE", None)


def _tool_name_from_event(event: SessionEvent) -> str:
    data = event.data
    for attr in ("tool_name", "name", "mcp_tool_name"):
        value = getattr(data, attr, None)
        if value:
            return str(value)
    return "tool"


@dataclass
class Streamer:
    """Consume Copilot ``SessionEvent`` callbacks for one session.

    Attach ``streamer.handler`` to ``session.on(...)``; after
    ``send_and_wait`` returns, call ``streamer.finish()`` to read the
    captured assistant text (with any trailing-newline side effects
    flushed to stdout for ``verbose`` / ``summary`` modes).

    ``on_tool_start`` / ``on_tool_end`` are fired (when the SDK surfaces
    those events) so callers can wire ``pre-tool-use`` / ``post-tool-use``
    hooks without re-implementing the event-type dispatch. They are
    invoked AFTER the streamer's own summary-mode bookkeeping, so a
    hook that writes to stdout won't interleave with a half-emitted
    summary line.
    """

    mode: StreamMode = "verbose"
    label: str = ""
    on_tool_start: ToolEventCb | None = None
    on_tool_end: ToolEventCb | None = None
    stream: TextIO | None = None

    _buffer: list[str] = field(default_factory=list, init=False, repr=False)
    _summary_announced: bool = field(default=False, init=False, repr=False)
    _finished: bool = field(default=False, init=False, repr=False)

    # ── public API ──────────────────────────────────────────────────────

    def handler(self, event: SessionEvent) -> None:
        etype = event.type
        if etype == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                self._buffer.append(delta)
                self._on_delta(delta)
            return
        if _TOOL_USE_START is not None and etype == _TOOL_USE_START:
            self._on_tool_start(event)
            if self.on_tool_start is not None:
                self.on_tool_start(event)
            return
        if _TOOL_USE_END is not None and etype == _TOOL_USE_END:
            self._on_tool_end(event)
            if self.on_tool_end is not None:
                self.on_tool_end(event)
            return

    @property
    def text(self) -> str:
        return "".join(self._buffer)

    def finish(self) -> str:
        """Flush trailing output and return the accumulated assistant text.

        Safe to call more than once — the side effect (newline / summary
        footer) only fires the first time.
        """
        if not self._finished:
            self._finished = True
            if self.mode == "verbose" and self._buffer:
                out = self._out()
                out.write("\n")
                out.flush()
            elif self.mode == "summary":
                prefix = self._prefix()
                out = self._out()
                out.write(f"{prefix}done ({len(self.text)} chars)\n")
                out.flush()
        return self.text

    # ── internals ───────────────────────────────────────────────────────

    def _out(self) -> Any:
        return self.stream if self.stream is not None else sys.stdout

    def _prefix(self) -> str:
        return f"[{self.label}] " if self.label else ""

    def _on_delta(self, delta: str) -> None:
        if self.mode == "verbose":
            out = self._out()
            out.write(delta)
            out.flush()
        elif self.mode == "summary":
            if not self._summary_announced:
                self._summary_announced = True
                out = self._out()
                out.write(f"{self._prefix()}generating...\n")
                out.flush()

    def _on_tool_start(self, event: SessionEvent) -> None:
        if self.mode == "summary":
            out = self._out()
            out.write(f"{self._prefix()}tool: {_tool_name_from_event(event)}\n")
            out.flush()

    def _on_tool_end(self, event: SessionEvent) -> None:
        # No per-tool footer in summary mode — the next event
        # (assistant delta or another tool) makes progress obvious.
        return None
