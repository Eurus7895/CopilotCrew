"""Shared fake Copilot SDK client for tests.

Lets tests drive ``crew.intent_router`` and ``crew.pipeline_runner`` without
touching the network. Patch ``crew.<module>.CopilotClient`` with
``make_fake_copilot_client(reply=...)`` to script a reply.
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


def make_fake_copilot_client(reply: str = "") -> Callable[..., FakeClient]:
    """Return a factory suitable for monkeypatching ``CopilotClient``.

    The monkeypatch replaces the ``CopilotClient`` name; calling it (as the
    production code does: ``CopilotClient()``) yields a fresh ``FakeClient``
    preloaded with the scripted reply.
    """
    clients: list[FakeClient] = []

    def _factory(*_args: Any, **_kwargs: Any) -> FakeClient:
        client = FakeClient(reply=reply)
        clients.append(client)
        return client

    _factory.clients = clients  # type: ignore[attr-defined]
    return _factory
