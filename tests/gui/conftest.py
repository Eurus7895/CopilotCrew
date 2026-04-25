"""Fixtures for GUI tests.

Skips every GUI test if ``fastapi`` isn't installed, so base-install CI
stays green.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from pathlib import Path

from fastapi.testclient import TestClient

from crew.gui.app import create_app
from crew.gui.config import GUIConfig


@pytest.fixture
def crew_home(tmp_path: Path) -> Path:
    (tmp_path / "outputs" / "daily-standup").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def gui_config(crew_home: Path) -> GUIConfig:
    return GUIConfig.build(
        crew_home=crew_home, model="test-model", user_name="Tester"
    )


@pytest.fixture
def client(gui_config: GUIConfig) -> TestClient:
    app = create_app(gui_config)
    return TestClient(app)
