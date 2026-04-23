"""GET / — full-shell rendering."""

from __future__ import annotations


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_home_renders_three_panes(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    # Chrome + panes
    assert "window-chrome" in html
    assert 'class="rail left-rail"' in html
    assert 'class="center"' in html
    assert 'class="rail right-rail"' in html
    # Header copy matches the mockup
    assert "Crew &mdash; your coworker" in html
    assert "Good morning" in html
    assert "what Crew remembers" in html


def test_home_seeds_gui_dir_and_memory(client, gui_config):
    client.get("/")
    assert (gui_config.gui_dir / "timeline.jsonl").exists()
    assert (gui_config.gui_dir / "pr_activity.jsonl").exists()
    assert (gui_config.gui_dir / "slack_mentions.jsonl").exists()
    assert (gui_config.gui_dir / "working_on.jsonl").exists()
    assert gui_config.memory_path.exists()


def test_home_shows_user_name_from_config(gui_config):
    from fastapi.testclient import TestClient
    from crew.gui.app import create_app
    from crew.gui.config import GUIConfig

    cfg = GUIConfig.build(
        crew_home=gui_config.crew_home, user_name="Eurus"
    )
    client = TestClient(create_app(cfg))
    r = client.get("/")
    assert "Good morning, Eurus" in r.text


def test_home_shows_post_to_standup_disabled(client):
    r = client.get("/")
    assert "Post to #standup" in r.text
    # Button is disabled until Slack integration lands.
    assert "disabled" in r.text
    assert "Slack integration coming" in r.text
