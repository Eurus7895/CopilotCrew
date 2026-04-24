"""Settings route + theme picker POST."""

from __future__ import annotations


def test_settings_page_renders_in_default_theme(client):
    r = client.get("/settings")
    assert r.status_code == 200
    html = r.text
    assert 'data-theme="warm"' in html
    assert "warm-settings" in html
    # All three theme options are listed as picker cards.
    assert "Warm · Workspace" in html
    assert "Terminal · Operator" in html
    assert "Modernist · Swiss" in html
    # The user's current theme is marked.
    assert "current" in html.lower()


def test_settings_page_marks_selected_theme(client):
    client.cookies.set("crew_theme", "terminal")
    r = client.get("/settings")
    assert r.status_code == 200
    assert 'data-theme="terminal"' in r.text
    assert "term-theme-row" in r.text


def test_settings_page_modernist_nav_wired(client):
    client.cookies.set("crew_theme", "modernist")
    r = client.get("/settings")
    html = r.text
    assert 'data-theme="modernist"' in html
    # Modernist's nav bar's "Settings" item links to /settings and is selected.
    assert 'href="/settings"' in html
    assert "mod-theme-row" in html


def test_post_theme_sets_cookie_and_redirects(client):
    r = client.post("/settings/theme/modernist", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings"
    assert r.cookies.get("crew_theme") == "modernist"


def test_post_theme_with_unknown_value_keeps_current(client):
    # Start as terminal; POST an unknown theme; should not flip.
    client.cookies.set("crew_theme", "terminal")
    r = client.post("/settings/theme/editorial", follow_redirects=False)
    assert r.status_code == 303
    assert r.cookies.get("crew_theme") == "terminal"


def test_home_after_theme_change_uses_new_theme(client):
    client.post("/settings/theme/modernist", follow_redirects=False)
    r = client.get("/")
    assert 'data-theme="modernist"' in r.text


def test_settings_has_back_link_to_home(client):
    r = client.get("/settings")
    assert 'href="/"' in r.text
