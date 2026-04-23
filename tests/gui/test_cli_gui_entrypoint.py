"""``crew gui`` CLI subcommand dispatch."""

from __future__ import annotations

import pytest

pytest.importorskip("copilot")  # CLI pulls crew.conversations → copilot SDK

from crew import cli


def test_gui_subcommand_dispatches_to_run_server(monkeypatch):
    calls: list[dict] = []

    def fake_run_server(**kw):
        calls.append(kw)

    # Inject the fake into the lazily-imported module before _run_gui hits it.
    import crew.gui.server as srv

    monkeypatch.setattr(srv, "run_server", fake_run_server)

    code = cli.main(["gui", "--port", "9999", "--host", "127.0.0.1"])
    assert code == 0
    assert calls == [{
        "host": "127.0.0.1",
        "port": 9999,
        "open_browser": False,
        "model": None,
    }]


def test_gui_subcommand_passes_open_and_model(monkeypatch):
    calls: list[dict] = []
    import crew.gui.server as srv
    monkeypatch.setattr(srv, "run_server", lambda **kw: calls.append(kw))

    code = cli.main(["gui", "--open", "--model", "gpt-4o"])
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
