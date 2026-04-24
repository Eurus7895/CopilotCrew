"""``crew gui`` CLI subcommand dispatch."""

from __future__ import annotations

import pytest

pytest.importorskip("copilot")  # CLI pulls crew.conversations → copilot SDK

from crew import cli


def test_gui_subcommand_defaults_open_window(monkeypatch):
    calls: list[dict] = []
    import crew.gui.server as srv
    monkeypatch.setattr(srv, "run_server", lambda **kw: calls.append(kw))

    code = cli.main(["gui"])
    assert code == 0
    assert calls == [{
        "host": "127.0.0.1",
        "port": None,            # ephemeral port by default
        "open_window": True,     # desktop window is the default
        "open_browser": False,
        "model": None,
    }]


def test_gui_subcommand_respects_no_window(monkeypatch):
    calls: list[dict] = []
    import crew.gui.server as srv
    monkeypatch.setattr(srv, "run_server", lambda **kw: calls.append(kw))

    code = cli.main(["gui", "--no-window", "--port", "9999"])
    assert code == 0
    assert calls[0]["open_window"] is False
    assert calls[0]["port"] == 9999


def test_gui_subcommand_passes_open_and_model(monkeypatch):
    calls: list[dict] = []
    import crew.gui.server as srv
    monkeypatch.setattr(srv, "run_server", lambda **kw: calls.append(kw))

    code = cli.main(["gui", "--no-window", "--open", "--model", "gpt-4o"])
    assert code == 0
    assert calls[0]["open_browser"] is True
    assert calls[0]["model"] == "gpt-4o"


def test_gui_subcommand_missing_extra_prints_hint(monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "crew.gui.server":
            raise ImportError("no fastapi")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    code = cli.main(["gui"])
    assert code == 2
    err = capsys.readouterr().err
    assert "pip install 'crew[gui]'" in err
