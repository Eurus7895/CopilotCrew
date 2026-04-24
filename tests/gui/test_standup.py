"""Standup draft: latest-output, skip, regenerate concurrency, disabled post."""

from __future__ import annotations

import asyncio
import time

import pytest


def _write(path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_draft_returns_empty_when_no_output(client):
    r = client.get("/standup/draft")
    assert r.status_code == 200
    assert "No draft yet" in r.text


def test_draft_returns_newest_file(client, gui_config):
    out = gui_config.outputs_dir / "daily-standup"
    older = out / "2026-04-22T08-00-00Z-aaaa.md"
    newer = out / "2026-04-23T08-00-00Z-bbbb.md"
    _write(older, "## Yesterday\n- old content\n")
    # Ensure distinct mtimes even on fast filesystems.
    time.sleep(0.02)
    _write(newer, "## Yesterday\n- new content\n")

    r = client.get("/standup/draft")
    assert r.status_code == 200
    assert "new content" in r.text
    assert "old content" not in r.text


def test_skip_deletes_latest(client, gui_config):
    out = gui_config.outputs_dir / "daily-standup"
    path = out / "2026-04-23T08-00-00Z-bbbb.md"
    _write(path, "content to be deleted")

    r = client.post("/standup/skip")
    assert r.status_code == 200
    assert not path.exists()
    # Response is the empty-state card partial.
    assert "No draft yet" in r.text


def test_post_to_slack_is_disabled(client):
    html = client.get("/").text
    # Primary button is the first labelled "Post to #standup" and carries disabled + tooltip.
    assert "Post to #standup" in html
    assert "disabled" in html
    assert "Slack integration coming" in html


def test_run_is_guarded_by_lock(monkeypatch, client):
    """Second click during an in-flight run returns 409."""
    from crew.gui.services import standup_service

    release = asyncio.Event()

    async def fake_generate(_cfg):  # noqa: ANN001 - signature matches
        async with standup_service._run_lock:
            await release.wait()

    monkeypatch.setattr(standup_service, "run_generate", fake_generate)

    # Kick off one run in the background — hold the lock.
    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(fake_generate(None))
        # Pump once so the lock is acquired before the second HTTP call.
        loop.run_until_complete(asyncio.sleep(0))
        assert standup_service.is_running()

        r = client.post("/standup/run")
        assert r.status_code == 409

        release.set()
        loop.run_until_complete(task)
    finally:
        loop.close()


def test_run_returns_202_when_idle(monkeypatch, client):
    from crew.gui.services import standup_service

    async def fake_generate(_cfg):  # noqa: ANN001
        return None

    monkeypatch.setattr(standup_service, "run_generate", fake_generate)
    r = client.post("/standup/run")
    assert r.status_code == 202
    assert r.headers.get("hx-trigger") == "standup-started"


def test_edit_without_draft_returns_404(client):
    r = client.post("/standup/edit")
    assert r.status_code == 404


def test_edit_calls_editor_when_draft_exists(monkeypatch, client, gui_config):
    from crew.gui.services import editor

    out = gui_config.outputs_dir / "daily-standup"
    path = out / "2026-04-23T08-00-00Z-bbbb.md"
    _write(path, "edit me")

    calls = []
    monkeypatch.setattr(editor, "open_in_editor", lambda p: calls.append(p) or True)

    r = client.post("/standup/edit")
    assert r.status_code == 204
    assert calls == [path]
