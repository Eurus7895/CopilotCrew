"""POST /pinned/<kind>/<name> — click a left-rail pinned item.

All three dispatch kinds (skill / agent / pipeline) return a chat-turn
fragment. The underlying service (``pinned_actions``) is stubbed so
tests don't need the Copilot SDK.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def stub_pinned(monkeypatch):
    """Stub every invoke_* to return a fixed message id without spawning a task."""
    from crew.gui.services import pinned_actions

    calls: list[tuple[str, str, str, str]] = []

    async def fake_skill(cfg, name, text):
        calls.append(("skill", name, text, "skillmsg"))
        return "skillmsg"

    async def fake_agent(cfg, name, text):
        calls.append(("agent", name, text, "agentmsg"))
        return "agentmsg"

    async def fake_pipeline(cfg, name, text):
        calls.append(("pipeline", name, text, "pipemsg"))
        return "pipemsg"

    monkeypatch.setattr(pinned_actions, "invoke_skill", fake_skill)
    monkeypatch.setattr(pinned_actions, "invoke_agent", fake_agent)
    monkeypatch.setattr(pinned_actions, "invoke_pipeline", fake_pipeline)
    return calls


def test_pinned_skill_returns_chat_turn(client, stub_pinned):
    r = client.post("/pinned/skill/debug", data={"message": "look at this error"})
    assert r.status_code == 200
    assert 'id="chat-msg-skillmsg"' in r.text
    assert "/debug look at this error" in r.text
    assert stub_pinned == [("skill", "debug", "look at this error", "skillmsg")]


def test_pinned_skill_without_message_uses_fallback(client, stub_pinned):
    r = client.post("/pinned/skill/debug")
    assert r.status_code == 200
    # Fallback prompt introduces the skill.
    assert stub_pinned[0][0] == "skill"
    assert "What does the /debug skill do" in stub_pinned[0][2]


def test_pinned_agent_returns_chat_turn(client, stub_pinned):
    r = client.post("/pinned/agent/coder", data={"message": "refactor this"})
    assert r.status_code == 200
    assert 'id="chat-msg-agentmsg"' in r.text
    assert "@coder" in r.text
    assert stub_pinned[0][:3] == ("agent", "coder", "refactor this")


def test_pinned_pipeline_returns_chat_turn(client, stub_pinned):
    r = client.post(
        "/pinned/pipeline/daily-standup", data={"message": "standup prep"}
    )
    assert r.status_code == 200
    assert 'id="chat-msg-pipemsg"' in r.text
    assert "/daily-standup" in r.text
    assert stub_pinned[0][:3] == ("pipeline", "daily-standup", "standup prep")


def test_pinned_memory_opens_editor(client, monkeypatch):
    from crew.gui.services import pinned_actions

    called = {}
    monkeypatch.setattr(pinned_actions, "open_memory", lambda cfg: called.setdefault("cfg", cfg) or True)

    r = client.post("/pinned/memory")
    assert r.status_code == 204
    assert "cfg" in called


def test_pinned_memory_without_editor_returns_400(client, monkeypatch):
    from crew.gui.services import pinned_actions

    monkeypatch.setattr(pinned_actions, "open_memory", lambda cfg: False)
    r = client.post("/pinned/memory")
    assert r.status_code == 400


def test_pinned_buttons_rendered_in_left_rail(client):
    html = client.get("/").text
    # Warm pins are now real buttons hitting /pinned/<kind>/<name>.
    assert 'hx-post="/pinned/' in html
    # Memory pin is wired too.
    assert 'hx-post="/pinned/memory"' in html
