"""Smoke tests for the desktop packaging path.

These verify the static pieces — the ``__main__`` entrypoint, the
PyInstaller spec file, and the build helper's CLI parsing. They do not
run PyInstaller itself (slow, platform-heavy, already covered by CI
builds).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "packaging" / "crew_gui.spec"
BUILD = REPO_ROOT / "packaging" / "build.py"


def test_desktop_entrypoint_boots_run_server(monkeypatch):
    """`python -m crew.gui` should hand off to ``run_server(open_window=True)``."""
    from crew.gui import __main__ as entry
    from crew.gui import server as server_mod

    called: list[dict] = []
    monkeypatch.setattr(server_mod, "run_server", lambda **kw: called.append(kw))
    entry.main()
    assert called == [{"open_window": True}]


def test_spec_file_is_syntactically_valid_python():
    """The spec is executed by PyInstaller as Python — it must parse cleanly."""
    source = SPEC.read_text(encoding="utf-8")
    ast.parse(source, filename=str(SPEC))  # raises SyntaxError if broken


def test_spec_file_references_bundle_data_paths():
    """Catch typos in the bundled-data paths by name-checking them."""
    source = SPEC.read_text(encoding="utf-8")
    for needed in ("crew/gui/templates", "crew/gui/static", "crew/gui/fixtures"):
        assert needed in source, f"spec must bundle {needed}"


def test_build_helper_shows_help():
    """The helper's --help runs without touching PyInstaller."""
    result = subprocess.run(
        [sys.executable, str(BUILD), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "PyInstaller" in result.stdout


def test_build_helper_errors_without_pyinstaller(monkeypatch, tmp_path):
    """If PyInstaller isn't installed, the helper exits 2 with a hint."""
    # Run the helper as a subprocess with PyInstaller hidden.
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT),
        # A scratch dir so we don't nuke the real dist/ if it exists.
        "HOME": str(tmp_path),
    }
    # Drop PyInstaller from the import path by pointing -S at a clean sys.path.
    script = (
        "import sys, runpy, builtins\n"
        "real_import = builtins.__import__\n"
        "def fake(name, *a, **kw):\n"
        "    if name == 'PyInstaller':\n"
        "        raise ImportError('not installed')\n"
        "    return real_import(name, *a, **kw)\n"
        "builtins.__import__ = fake\n"
        f"sys.argv = ['build.py']\n"
        f"runpy.run_path(r'{BUILD}', run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert result.returncode == 2
    assert "PyInstaller is not installed" in result.stderr
