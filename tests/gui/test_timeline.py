"""Timeline event swapping."""

from __future__ import annotations


def test_timeline_event_returns_full_page_without_hx(client):
    r = client.get("/timeline/morning")
    assert r.status_code == 200
    # Full shell: the window is the entire app — no external page header.
    assert 'data-theme="warm"' in r.text
    assert "warm-window" in r.text


def test_timeline_event_returns_fragment_with_hx_request(client):
    r = client.get("/timeline/nudge", headers={"HX-Request": "true"})
    assert r.status_code == 200
    # Fragment must not include the full window shell.
    assert "warm-window" not in r.text
    # But it must include the theme's center timeline article.
    assert "warm-moment" in r.text


def test_timeline_event_respects_theme_cookie_for_fragment(client):
    r = client.get(
        "/timeline/nudge",
        headers={"HX-Request": "true"},
        cookies={"crew_theme": "modernist"},
    )
    assert r.status_code == 200
    # Modernist uses the §NN section marker + mod-entry article.
    assert "mod-entry" in r.text
    assert "warm-moment" not in r.text


def test_unknown_timeline_event_returns_404(client):
    r = client.get("/timeline/does-not-exist")
    assert r.status_code == 404
