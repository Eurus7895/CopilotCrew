"""Tests for the shared ``crew.streamer`` module.

Covers the three modes (``verbose`` / ``summary`` / ``silent``), tool-event
callbacks for ``pre-tool-use`` / ``post-tool-use`` hook wiring, and the
idempotent-flush behaviour of ``finish()``.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from copilot.generated.session_events import SessionEventType

from crew.streamer import Streamer


@dataclass
class _FakeData:
    delta_content: str | None = None
    tool_name: str | None = None


@dataclass
class _FakeEvent:
    type: object
    data: _FakeData


def _delta(text: str) -> _FakeEvent:
    return _FakeEvent(
        type=SessionEventType.ASSISTANT_MESSAGE_DELTA,
        data=_FakeData(delta_content=text),
    )


def _tool_start(name: str = "github.list_prs") -> _FakeEvent:
    return _FakeEvent(
        type=SessionEventType.TOOL_EXECUTION_START,
        data=_FakeData(tool_name=name),
    )


def _tool_end(name: str = "github.list_prs") -> _FakeEvent:
    return _FakeEvent(
        type=SessionEventType.TOOL_EXECUTION_COMPLETE,
        data=_FakeData(tool_name=name),
    )


# ── verbose mode ────────────────────────────────────────────────────────────


def test_verbose_streams_every_delta_to_stream() -> None:
    out = io.StringIO()
    s = Streamer(mode="verbose", stream=out)

    s.handler(_delta("Hello, "))
    s.handler(_delta("world!"))
    text = s.finish()

    assert text == "Hello, world!"
    # Deltas are echoed, then finish() appends a trailing newline.
    assert out.getvalue() == "Hello, world!\n"


def test_verbose_finish_without_deltas_writes_nothing() -> None:
    """No assistant deltas means no newline — nothing to terminate."""
    out = io.StringIO()
    s = Streamer(mode="verbose", stream=out)
    assert s.finish() == ""
    assert out.getvalue() == ""


def test_finish_is_idempotent() -> None:
    out = io.StringIO()
    s = Streamer(mode="verbose", stream=out)
    s.handler(_delta("hi"))
    first = s.finish()
    second = s.finish()
    assert first == second == "hi"
    # Trailing newline only fires once.
    assert out.getvalue().count("\n") == 1


# ── summary mode ────────────────────────────────────────────────────────────


def test_summary_announces_once_then_prints_done_with_char_count() -> None:
    out = io.StringIO()
    s = Streamer(mode="summary", stream=out, label="demo")

    s.handler(_delta("chunk one"))
    s.handler(_delta(" and chunk two"))
    s.finish()

    value = out.getvalue()
    # Single "generating..." line even with two deltas.
    assert value.count("generating") == 1
    assert "[demo] generating..." in value
    # Footer with char count.
    assert f"[demo] done ({len('chunk one and chunk two')} chars)" in value


def test_summary_prints_tool_lines_and_fires_callbacks() -> None:
    out = io.StringIO()
    tool_starts: list[_FakeEvent] = []
    tool_ends: list[_FakeEvent] = []
    s = Streamer(
        mode="summary",
        stream=out,
        label="run",
        on_tool_start=tool_starts.append,
        on_tool_end=tool_ends.append,
    )

    s.handler(_tool_start("github.list_prs"))
    s.handler(_tool_end("github.list_prs"))
    s.handler(_delta("final answer"))
    s.finish()

    value = out.getvalue()
    assert "[run] tool: github.list_prs" in value
    assert len(tool_starts) == 1
    assert len(tool_ends) == 1
    # The delta still triggers the generating announcement exactly once.
    assert value.count("generating") == 1


def test_summary_no_label_still_works() -> None:
    out = io.StringIO()
    s = Streamer(mode="summary", stream=out)
    s.handler(_delta("x"))
    s.finish()
    value = out.getvalue()
    # No bracketed prefix when label is empty.
    assert "generating..." in value
    assert "[ " not in value
    assert "done (1 chars)" in value


# ── silent mode ─────────────────────────────────────────────────────────────


def test_silent_captures_but_never_writes() -> None:
    out = io.StringIO()
    s = Streamer(mode="silent", stream=out)
    s.handler(_delta("captured"))
    s.handler(_tool_start())
    s.handler(_tool_end())
    assert s.finish() == "captured"
    assert out.getvalue() == ""


def test_silent_still_fires_tool_callbacks() -> None:
    """The evaluator + router use silent mode but shouldn't need tool callbacks
    — still, the contract is that user-supplied callbacks always fire.
    """
    tool_starts: list[_FakeEvent] = []
    s = Streamer(mode="silent", on_tool_start=tool_starts.append)
    s.handler(_tool_start("x"))
    assert len(tool_starts) == 1


# ── event dispatch ──────────────────────────────────────────────────────────


def test_handler_ignores_empty_deltas() -> None:
    out = io.StringIO()
    s = Streamer(mode="verbose", stream=out)
    s.handler(_delta(""))  # no content
    s.handler(_FakeEvent(type=SessionEventType.ASSISTANT_MESSAGE_DELTA, data=_FakeData()))
    assert s.text == ""
    assert s.finish() == ""
    assert out.getvalue() == ""


def test_handler_ignores_unrelated_event_types() -> None:
    out = io.StringIO()
    s = Streamer(mode="verbose", stream=out)
    s.handler(_FakeEvent(type=SessionEventType.SESSION_START, data=_FakeData()))
    s.handler(_FakeEvent(type=SessionEventType.USER_MESSAGE, data=_FakeData()))
    assert s.text == ""
    assert out.getvalue() == ""


def test_text_property_reflects_buffer_before_finish() -> None:
    s = Streamer(mode="silent")
    s.handler(_delta("partial"))
    assert s.text == "partial"
    s.handler(_delta(" more"))
    assert s.text == "partial more"
