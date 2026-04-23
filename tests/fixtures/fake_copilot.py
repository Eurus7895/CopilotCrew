"""Shared fake Copilot SDK client for tests.

Lets tests drive ``crew.intent_router``, ``crew.pipeline_runner``, and
``crew.evaluator`` without touching the network. Patch
``crew.<module>.CopilotClient`` with ``make_fake_copilot_client(reply=...)``
for a single canned response, or ``make_fake_copilot_client(replies=[...])``
to script a different reply for each successive ``CopilotClient()``
instantiation (useful for the Level 1 generator → evaluator → retry flow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FakeEventData:
    delta_content: str | None = None


@dataclass
class FakeEvent:
    type: Any
    data: FakeEventData


@dataclass
class FakeSession:
    reply: str
    sent: list[str] = field(default_factory=list)
    listeners: list[Callable[[FakeEvent], None]] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)

    def on(self, fn: Callable[[FakeEvent], None]) -> None:
        self.listeners.append(fn)

    async def send_and_wait(self, prompt: str) -> None:
        self.sent.append(prompt)
        from copilot.generated.session_events import SessionEventType

        for chunk in _chunks(self.reply):
            event = FakeEvent(
                type=SessionEventType.ASSISTANT_MESSAGE_DELTA,
                data=FakeEventData(delta_content=chunk),
            )
            for fn in list(self.listeners):
                fn(event)

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@dataclass
class FakeClient:
    reply: str
    sessions: list[FakeSession] = field(default_factory=list)

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def create_session(self, **kwargs: Any) -> FakeSession:
        session = FakeSession(reply=self.reply, kwargs=dict(kwargs))
        self.sessions.append(session)
        return session


def _chunks(text: str, size: int = 32) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def make_fake_copilot_client(
    reply: str | None = None,
    *,
    replies: list[str] | None = None,
) -> Callable[..., FakeClient]:
    """Return a factory suitable for monkeypatching ``CopilotClient``.

    ``reply=`` (back-compat): every constructed client uses the same string.
    ``replies=`` (sequencing): each successive ``CopilotClient()`` pops the
    next entry from the list. Exhausting the list raises ``IndexError`` with
    a message that names the test fixture (so test failures are diagnosable).
    """
    if reply is not None and replies is not None:
        raise ValueError("pass either `reply=` or `replies=`, not both")
    if reply is None and replies is None:
        reply = ""

    clients: list[FakeClient] = []
    queue: list[str] | None = list(replies) if replies is not None else None

    def _factory(*_args: Any, **_kwargs: Any) -> FakeClient:
        if queue is not None:
            if not queue:
                raise IndexError(
                    "fake copilot ran out of scripted replies "
                    f"(already produced {len(clients)} client(s))"
                )
            next_reply = queue.pop(0)
        else:
            next_reply = reply  # type: ignore[assignment]
        client = FakeClient(reply=next_reply)
        clients.append(client)
        return client

    _factory.clients = clients  # type: ignore[attr-defined]
    return _factory
