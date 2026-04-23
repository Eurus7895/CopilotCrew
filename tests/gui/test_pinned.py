"""Pinned rail merges skills + agents + pipelines."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from crew.gui.services import pinned


@dataclass
class _P:
    name: str
    description: str = ""


@dataclass
class _A:
    name: str
    description: str = ""
    standalone: bool = True


@pytest.fixture
def stub_registries(monkeypatch):
    monkeypatch.setattr(
        "crew.gui.services.pinned.pipeline_registry.discover",
        lambda: [_P("daily-standup", "standup")],
    )
    monkeypatch.setattr(
        "crew.gui.services.pinned.skill_registry.discover",
        lambda: [_P("debug", "debug")],
    )
    monkeypatch.setattr(
        "crew.gui.services.pinned.agent_registry.discover",
        lambda: [
            _A("coder", "coder persona", True),
            _A("internal", "subagent only", False),
        ],
    )


def test_assemble_merges_all_three_registries(stub_registries):
    items = pinned.assemble()
    labels = [i.label for i in items]
    assert "/daily-standup" in labels
    assert "/debug" in labels
    assert "agent:coder" in labels


def test_assemble_skips_non_standalone_agents(stub_registries):
    items = pinned.assemble()
    labels = [i.label for i in items]
    assert "agent:internal" not in labels


def test_assemble_kinds_are_tagged(stub_registries):
    by_label = {i.label: i for i in pinned.assemble()}
    assert by_label["/daily-standup"].kind == "pipeline"
    assert by_label["/debug"].kind == "skill"
    assert by_label["agent:coder"].kind == "agent"
