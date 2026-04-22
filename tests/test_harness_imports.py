"""Smoke test for the CopilotHarness@dev port.

A passing import means the package-relative imports + path-constant rewrites
are internally consistent. Behavioural tests come back as the modules get
wired up by Day 2+ pipelines.
"""


def test_harness_modules_import():
    from crew.harness import (  # noqa: F401
        agent_loader,
        context_builder,
        correction_loop,
        executor,
        skill_loader,
        state,
        verifier,
    )
    from crew.harness.memory import pattern_detector  # noqa: F401
    from crew.harness.storage import db  # noqa: F401
