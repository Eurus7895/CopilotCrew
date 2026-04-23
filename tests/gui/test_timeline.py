"""Timeline event swapping."""

from __future__ import annotations


def test_timeline_event_returns_full_page_without_hx(client):
    r = client.get("/timeline/morning")
    assert r.status_code == 200
    # Full shell has the page header.
    assert "page-head" in r.text


def test_timeline_event_returns_fragment_with_hx_request(client):
    r = client.get("/timeline/nudge", headers={"HX-Request": "true"})
    assert r.status_code == 200
    # Fragment must not include the outer chrome.
    assert "page-head" not in r.text
    assert "window-chrome" not in r.text
    # But it must include a center moment article and an oob-swapped right rail.
    assert "moment-title" in r.text
    assert 'hx-swap-oob' in r.text


def test_unknown_timeline_event_returns_404(client):
    r = client.get("/timeline/does-not-exist")
    assert r.status_code == 404
