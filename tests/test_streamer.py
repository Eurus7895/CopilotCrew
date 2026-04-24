"""Unit tests for ``crew.streamer``."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("copilot")  # streamer imports SessionEventType

from crew.streamer import (
    CallbackStreamer,
    Streamer,
    SummaryStreamer,
    TerminalStreamer,
)

from fake_copilot import FakeEvent, FakeEventData  # from tests/fixtures
from copilot.generated.session_events import SessionEventType


def _delta_event(text: str) -> FakeEvent:
    return FakeEvent(
        type=SessionEventType.ASSISTANT_MESSAGE_DELTA,
        data=FakeEventData(delta_content=text),
    )


def test_summary_streamer_collects_silently(capsys):
    s = SummaryStreamer()
    s.handle_event(_delta_event("hel"))
    s.handle_event(_delta_event("lo"))
    assert s.text == "hello"
    # Must not print anything.
    captured = capsys.readouterr()
    assert captured.out == ""


def test_terminal_streamer_writes_to_stdout(capsys):
    s = TerminalStreamer()
    s.handle_event(_delta_event("hel"))
    s.handle_event(_delta_event("lo"))
    s.finish_line()
    captured = capsys.readouterr()
    assert captured.out == "hello\n"
    assert s.text == "hello"


def test_callback_streamer_fans_out_deltas():
    chunks: list[str] = []
    s = CallbackStreamer(on_delta_fn=chunks.append)
    s.handle_event(_delta_event("a"))
    s.handle_event(_delta_event("b"))
    s.handle_event(_delta_event("c"))
    assert chunks == ["a", "b", "c"]
    assert s.text == "abc"


def test_callback_streamer_ignores_empty_delta():
    chunks: list[str] = []
    s = CallbackStreamer(on_delta_fn=chunks.append)
    s.handle_event(_delta_event(""))
    assert chunks == []
    assert s.text == ""


def test_callback_streamer_without_sink_is_noop():
    s = CallbackStreamer()
    s.handle_event(_delta_event("hi"))
    # Still buffers.
    assert s.text == "hi"


def test_base_streamer_ignores_non_delta_events():
    s = SummaryStreamer()

    @dataclass
    class _OtherEvent:
        type: object = object()
        data: object = object()

    s.handle_event(_OtherEvent())  # type: ignore[arg-type]
    assert s.text == ""
