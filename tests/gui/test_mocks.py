"""JSONL readers tolerate missing / malformed input."""

from __future__ import annotations

import pytest

from crew.gui.services import mocks


def test_missing_files_return_empty(gui_config):
    # gui_config is a fresh tmp; nothing seeded yet.
    assert mocks.load_timeline(gui_config) == []
    assert mocks.load_pr_activity(gui_config) == []
    assert mocks.load_slack_mentions(gui_config) == []
    assert mocks.load_working_on(gui_config) == []
    assert mocks.load_facts(gui_config) == []


def test_malformed_lines_are_skipped(gui_config):
    gui_config.gui_dir.mkdir(parents=True, exist_ok=True)
    path = gui_config.gui_dir / "timeline.jsonl"
    path.write_text(
        '{"id": "ok", "label": "fine"}\n'
        "not json at all\n"
        '{"id": "also-ok", "label": "fine2"}\n',
        encoding="utf-8",
    )
    rows = mocks.load_timeline(gui_config)
    ids = [r["id"] for r in rows]
    assert ids == ["ok", "also-ok"]


def test_load_timeline_event_matches_by_id(gui_config):
    gui_config.gui_dir.mkdir(parents=True, exist_ok=True)
    (gui_config.gui_dir / "timeline.jsonl").write_text(
        '{"id": "a", "label": "alpha"}\n{"id": "b", "label": "beta"}\n',
        encoding="utf-8",
    )
    assert mocks.load_timeline_event(gui_config, "b") == {"id": "b", "label": "beta"}
    assert mocks.load_timeline_event(gui_config, "missing") is None
