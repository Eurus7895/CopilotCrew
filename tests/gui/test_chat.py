"""POST /chat — user bubble + placeholder assistant bubble + task spawn.

The heavy lifting (Copilot SDK call) runs in a background task and
publishes tokens onto the events bus; we stub ``chat_service.send_message``
so tests don't need the SDK or an event loop.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def stub_send(monkeypatch):
    """Make send_message return a predictable ChatEchoed without spawning a
    background task."""
    from crew.gui.services import chat_service

    recorded: list[tuple[object, str]] = []

    async def fake_send(cfg, text):
        recorded.append((cfg, text))
        return chat_service.ChatEchoed(message_id="fixedid123", user_text=text)

    monkeypatch.setattr(chat_service, "send_message", fake_send)
    return recorded


def test_chat_echoes_user_and_stubs_assistant(client, stub_send):
    r = client.post("/chat", data={"message": "standup status?"})
    assert r.status_code == 200
    html = r.text
    # Warm theme is default — user bubble + placeholder assistant bubble.
    assert "warm-bubble-user" in html
    assert "warm-bubble-crew" in html
    assert "standup status?" in html
    # Assistant bubble has the id the JS streamer will target.
    assert 'id="chat-msg-fixedid123"' in html
    # Streaming sentinel attribute present.
    assert 'data-state="streaming"' in html
    # Service received the message.
    assert stub_send == [(client.app.state.cfg, "standup status?")]


def test_chat_rejects_empty_message(client, stub_send):
    r = client.post("/chat", data={"message": "   "})
    assert r.status_code == 400
    assert stub_send == []


def test_chat_respects_theme_cookie(client, stub_send):
    client.cookies.set("crew_theme", "modernist")
    r = client.post("/chat", data={"message": "hi"})
    assert r.status_code == 200
    # Modernist uses a different bubble class.
    assert "mod-bubble-user" in r.text
    assert "mod-bubble-crew" in r.text


def test_chat_respects_terminal_theme(client, stub_send):
    client.cookies.set("crew_theme", "terminal")
    r = client.post("/chat", data={"message": "log me in"}).text
    assert "term-bubble-user" in r
    assert "term-bubble-crew" in r
    # Terminal prompts render.
    assert "crew&rsaquo;" in r or "crew›" in r


def test_home_exposes_chat_log_and_composer(client):
    html = client.get("/").text
    assert 'id="chat-log"' in html
    # Warm composer is an HTMX form hitting /chat.
    assert 'hx-post="/chat"' in html
    assert 'name="message"' in html
