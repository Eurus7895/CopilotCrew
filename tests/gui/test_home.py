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
    # Default theme is warm — its shell owns the three panes.
    assert 'data-theme="warm"' in html
    assert "warm-window" in html
    assert "warm-left" in html
    assert "warm-center" in html
    assert "warm-right" in html
    # Header copy matches the four-directions mockup.
    assert "Crew &mdash; four directions" in html
    assert "Good morning" in html
    # Tab strip includes all three design languages.
    assert "Warm · Workspace" in html
    assert "Terminal · Operator" in html
    assert "Modernist · Swiss" in html


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
    assert "disabled" in r.text
    assert "Slack integration coming" in r.text


def test_home_switches_theme_via_query_param(client):
    r = client.get("/?theme=terminal")
    assert r.status_code == 200
    assert 'data-theme="terminal"' in r.text
    # Terminal theme uses the tmux-style window and path-based section heads.
    assert "term-window" in r.text
    assert "~/SESSIONS" in r.text
    assert "crew&gt;" in r.text
    # Cookie is persisted.
    assert r.cookies.get("crew_theme") == "terminal"


def test_home_switches_theme_to_modernist(client):
    r = client.get("/?theme=modernist")
    assert r.status_code == 200
    assert 'data-theme="modernist"' in r.text
    # Modernist uses giant numerals and BY THE NUMBERS rail.
    assert "mod-numeral" in r.text
    assert "By the numbers" in r.text
    assert "The day, measured." in r.text


def test_home_unknown_theme_falls_back_to_default(client):
    r = client.get("/?theme=nope")
    assert r.status_code == 200
    assert 'data-theme="warm"' in r.text


def test_home_reads_theme_cookie(client):
    r = client.get("/", cookies={"crew_theme": "terminal"})
    assert 'data-theme="terminal"' in r.text
