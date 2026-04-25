"""Assemble the left-rail PINNED section from real registries."""

from __future__ import annotations

from dataclasses import dataclass

from crew import agent_registry, pipeline_registry, skill_registry


@dataclass(frozen=True)
class PinnedItem:
    label: str          # displayed text, e.g. "/standup" or "agent:coder"
    kind: str           # "pipeline" | "skill" | "agent"
    name: str           # raw registry name
    description: str


def assemble() -> list[PinnedItem]:
    """Merge all three registries into a single pinned list.

    Ordering: pipelines → skills → agents. Failures discover-side are
    already swallowed in each registry, so this never raises.
    """
    out: list[PinnedItem] = []

    for p in pipeline_registry.discover():
        out.append(
            PinnedItem(
                label=f"/{p.name}",
                kind="pipeline",
                name=p.name,
                description=p.description,
            )
        )

    for s in skill_registry.discover():
        out.append(
            PinnedItem(
                label=f"/{s.name}",
                kind="skill",
                name=s.name,
                description=s.description,
            )
        )

    for a in agent_registry.discover():
        if not a.standalone:
            continue
        out.append(
            PinnedItem(
                label=f"agent:{a.name}",
                kind="agent",
                name=a.name,
                description=a.description,
            )
        )

    return out
