import asyncio
import json
import logging
from pathlib import Path

import pytest

from crew import conversations
from fake_copilot import make_fake_copilot_client


def _run(coro):
    return asyncio.run(coro)


# ── Scope keys ───────────────────────────────────────────────────────────────


def test_compute_scope_is_stable_across_calls(tmp_path: Path) -> None:
    a = conversations.compute_scope(cwd=tmp_path, mode="direct", agent=None)
    b = conversations.compute_scope(cwd=tmp_path, mode="direct", agent=None)
    assert a == b


def test_compute_scope_varies_by_mode(tmp_path: Path) -> None:
    direct = conversations.compute_scope(cwd=tmp_path, mode="direct", agent=None)
    agent = conversations.compute_scope(cwd=tmp_path, mode="agent", agent="coder")
    assert direct != agent


def test_compute_scope_varies_by_agent(tmp_path: Path) -> None:
    coder = conversations.compute_scope(cwd=tmp_path, mode="agent", agent="coder")
    review = conversations.compute_scope(cwd=tmp_path, mode="agent", agent="reviewer")
    assert coder != review


def test_compute_scope_varies_by_cwd(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    sa = conversations.compute_scope(cwd=a, mode="direct", agent=None)
    sb = conversations.compute_scope(cwd=b, mode="direct", agent=None)
    assert sa != sb


def test_named_scope_is_global(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    sa = conversations.compute_scope(cwd=a, mode="direct", named="refactor-x")
    sb = conversations.compute_scope(cwd=b, mode="agent", agent="coder", named="refactor-x")
    # Named sessions ignore mode / agent / cwd.
    assert sa == sb
    assert sa.startswith("named__")


def test_compute_scope_is_filesystem_safe(tmp_path: Path) -> None:
    scope = conversations.compute_scope(
        cwd=tmp_path, mode="agent", agent="coder", named=None
    )
    # Must be a valid filename (no slashes, colons, spaces).
    forbidden = {"/", "\\", ":", " ", "?", "*", "<", ">", "|", '"'}
    assert not (forbidden & set(scope))


# ── save / load / clear ──────────────────────────────────────────────────────


def test_save_load_roundtrip(tmp_path: Path) -> None:
    scope = "test__a__abc123"
    state = conversations.save_session(
        scope,
        session_id="sess_1",
        turn_count=3,
        cwd=tmp_path,
        mode="direct",
        agent=None,
        named=None,
        crew_home=tmp_path,
    )
    assert state.session_id == "sess_1"
    assert state.turn_count == 3

    loaded = conversations.load_session(scope, crew_home=tmp_path)
    assert loaded is not None
    assert loaded.session_id == "sess_1"
    assert loaded.turn_count == 3
    assert loaded.cwd == str(tmp_path.resolve())


def test_load_returns_none_for_unknown_scope(tmp_path: Path) -> None:
    assert conversations.load_session("nope", crew_home=tmp_path) is None


def test_save_preserves_started_at_across_updates(tmp_path: Path) -> None:
    scope = "x"
    first = conversations.save_session(
        scope,
        session_id="sess_1",
        turn_count=1,
        cwd=tmp_path,
        mode="direct",
        agent=None,
        named=None,
        crew_home=tmp_path,
    )
    second = conversations.save_session(
        scope,
        session_id="sess_1",
        turn_count=2,
        cwd=tmp_path,
        mode="direct",
        agent=None,
        named=None,
        crew_home=tmp_path,
    )
    assert first.started_at == second.started_at
    # last_used updates on each save.
    assert second.last_used >= first.last_used


def test_clear_session_drops_state_and_jsonl(tmp_path: Path) -> None:
    scope = "x"
    conversations.save_session(
        scope,
        session_id="sess_1",
        turn_count=1,
        cwd=tmp_path,
        mode="direct",
        agent=None,
        named=None,
        crew_home=tmp_path,
    )
    conversations.append_turn(
        scope,
        mode="direct",
        agent=None,
        user="hi",
        assistant="hello",
        session_id="sess_1",
        crew_home=tmp_path,
    )
    assert conversations.load_session(scope, crew_home=tmp_path) is not None
    assert (tmp_path / "conversations" / f"{scope}.jsonl").exists()

    removed = conversations.clear_session(scope, crew_home=tmp_path)
    assert removed is True
    assert conversations.load_session(scope, crew_home=tmp_path) is None
    assert not (tmp_path / "conversations" / f"{scope}.jsonl").exists()


def test_clear_missing_scope_is_noop(tmp_path: Path) -> None:
    assert conversations.clear_session("nope", crew_home=tmp_path) is False


def test_clear_all_drops_every_scope(tmp_path: Path) -> None:
    for n in ("a", "b", "c"):
        conversations.save_session(
            n,
            session_id=f"sess_{n}",
            turn_count=1,
            cwd=tmp_path,
            mode="direct",
            agent=None,
            named=None,
            crew_home=tmp_path,
        )
    count = conversations.clear_all(crew_home=tmp_path)
    assert count == 3
    assert conversations.list_scope_keys(crew_home=tmp_path) == []


def test_corrupt_sessions_json_is_treated_as_empty(
    tmp_path: Path, caplog
) -> None:
    (tmp_path / "sessions.json").write_text("not json{{", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="crew.conversations"):
        assert conversations.load_session("x", crew_home=tmp_path) is None
    assert any("could not read" in r.message for r in caplog.records)


# ── append_turn / tail / append_event ────────────────────────────────────────


def test_append_turn_writes_jsonl_row(tmp_path: Path) -> None:
    scope = "x"
    conversations.append_turn(
        scope,
        mode="direct",
        agent=None,
        user="hi",
        assistant="hello",
        session_id="sess_1",
        crew_home=tmp_path,
    )
    rows = conversations.tail(scope, crew_home=tmp_path)
    assert len(rows) == 1
    assert rows[0]["type"] == "turn"
    assert rows[0]["user"] == "hi"
    assert rows[0]["assistant"] == "hello"
    assert rows[0]["session_id"] == "sess_1"
    assert "ts" in rows[0]


def test_append_turn_appends_in_order(tmp_path: Path) -> None:
    scope = "x"
    for i in range(3):
        conversations.append_turn(
            scope,
            mode="agent",
            agent="coder",
            user=f"u{i}",
            assistant=f"a{i}",
            session_id="sess",
            crew_home=tmp_path,
        )
    rows = conversations.tail(scope, crew_home=tmp_path)
    assert [r["user"] for r in rows] == ["u0", "u1", "u2"]


def test_append_event_marks_rotations(tmp_path: Path) -> None:
    scope = "x"
    conversations.append_event(
        scope, "rotated", {"old_session_id": "sess_1"}, crew_home=tmp_path
    )
    rows = conversations.tail(scope, crew_home=tmp_path)
    assert rows[0]["type"] == "event"
    assert rows[0]["event"] == "rotated"
    assert rows[0]["old_session_id"] == "sess_1"


def test_tail_returns_last_n_rows(tmp_path: Path) -> None:
    scope = "x"
    for i in range(5):
        conversations.append_turn(
            scope,
            mode="direct",
            agent=None,
            user=f"u{i}",
            assistant="a",
            session_id="sess",
            crew_home=tmp_path,
        )
    last2 = conversations.tail(scope, n=2, crew_home=tmp_path)
    assert [r["user"] for r in last2] == ["u3", "u4"]


def test_tail_skips_corrupt_lines(tmp_path: Path) -> None:
    scope = "x"
    p = tmp_path / "conversations" / f"{scope}.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(
        '{"type":"turn","user":"ok","assistant":"yes","session_id":"s"}\n'
        "this is not json\n"
        '{"type":"turn","user":"again","assistant":"y","session_id":"s"}\n',
        encoding="utf-8",
    )
    rows = conversations.tail(scope, crew_home=tmp_path)
    assert [r["user"] for r in rows] == ["ok", "again"]


# ── should_rotate ────────────────────────────────────────────────────────────


def test_should_rotate_at_cap(tmp_path: Path) -> None:
    state = conversations.SessionState(
        session_id="s",
        turn_count=20,
        cwd=str(tmp_path),
        mode="direct",
        agent=None,
        named=None,
        started_at="t",
        last_used="t",
    )
    assert conversations.should_rotate(state, cap=20) is True
    assert conversations.should_rotate(state, cap=21) is False


def test_should_rotate_returns_false_for_none() -> None:
    assert conversations.should_rotate(None) is False


def test_turn_cap_default_uses_env(monkeypatch) -> None:
    monkeypatch.setenv("CREW_TURN_CAP", "5")
    # The constant is read at import time, so re-evaluate via the helper.
    assert conversations._turn_cap_default() == 5


def test_turn_cap_default_falls_back_on_invalid(monkeypatch, caplog) -> None:
    monkeypatch.setenv("CREW_TURN_CAP", "not-a-number")
    with caplog.at_level(logging.WARNING, logger="crew.conversations"):
        assert conversations._turn_cap_default() == 20


# ── list_scopes ──────────────────────────────────────────────────────────────


def test_list_scopes_returns_states_in_order(tmp_path: Path) -> None:
    for n in ("zzz", "aaa", "mmm"):
        conversations.save_session(
            n,
            session_id=f"sess_{n}",
            turn_count=1,
            cwd=tmp_path,
            mode="direct",
            agent=None,
            named=None,
            crew_home=tmp_path,
        )
    scopes = conversations.list_scopes(crew_home=tmp_path)
    assert [s.session_id for s in scopes] == ["sess_aaa", "sess_mmm", "sess_zzz"]


# ── render_session_table ─────────────────────────────────────────────────────


def test_render_session_table_handles_empty() -> None:
    assert "no sessions" in conversations.render_session_table([])


def test_render_session_table_shows_named_as_any_cwd(tmp_path: Path) -> None:
    state = conversations.save_session(
        "named__abc",
        session_id="sess",
        turn_count=4,
        cwd=tmp_path,
        mode="direct",
        agent=None,
        named="refactor-x",
        crew_home=tmp_path,
    )
    rendered = conversations.render_session_table([state])
    assert "named:refactor-x" in rendered
    assert "(any cwd)" in rendered
    assert "4 turns" in rendered


# ── summarize_for_rotation ───────────────────────────────────────────────────


def test_summarize_returns_no_context_when_empty(tmp_path: Path) -> None:
    out = _run(
        conversations.summarize_for_rotation(
            "missing", model=None, crew_home=tmp_path
        )
    )
    assert out == "(no prior context)"


def test_summarize_invokes_sdk_with_isolated_session(
    monkeypatch, tmp_path: Path
) -> None:
    factory = make_fake_copilot_client(
        reply="Goal: ship Day 4-A.\nDecisions: …\nOpen questions: …\n"
    )
    monkeypatch.setattr(conversations, "CopilotClient", factory)

    scope = "x"
    conversations.append_turn(
        scope,
        mode="direct",
        agent=None,
        user="how do I ship Day 4-A?",
        assistant="open conversations.py",
        session_id="sess_1",
        crew_home=tmp_path,
    )

    summary = _run(
        conversations.summarize_for_rotation(scope, model=None, crew_home=tmp_path)
    )
    assert "Goal" in summary
    session = factory.clients[-1].sessions[-1]
    # Same isolation rules as the evaluator: no MCP, replace-mode system prompt,
    # no permission handler (no tools).
    assert session.kwargs["enable_config_discovery"] is False
    assert "on_permission_request" not in session.kwargs
    assert session.kwargs["system_message"]["mode"] == "replace"
    assert "compress" in session.kwargs["system_message"]["content"].lower()


def test_summary_model_override(monkeypatch) -> None:
    monkeypatch.setenv("CREW_SUMMARY_MODEL", "gpt-mini")
    assert conversations._resolve_summary_model("gpt-4.1") == "gpt-mini"


def test_summary_model_falls_back_to_user_model(monkeypatch) -> None:
    monkeypatch.delenv("CREW_SUMMARY_MODEL", raising=False)
    assert conversations._resolve_summary_model("gpt-4.1") == "gpt-4.1"


def test_summary_is_not_logged_to_jsonl(monkeypatch, tmp_path: Path) -> None:
    factory = make_fake_copilot_client(reply="summary")
    monkeypatch.setattr(conversations, "CopilotClient", factory)

    scope = "x"
    conversations.append_turn(
        scope,
        mode="direct",
        agent=None,
        user="u",
        assistant="a",
        session_id="sess",
        crew_home=tmp_path,
    )
    rows_before = conversations.tail(scope, crew_home=tmp_path)
    _run(conversations.summarize_for_rotation(scope, crew_home=tmp_path))
    rows_after = conversations.tail(scope, crew_home=tmp_path)
    # Summary call MUST NOT pollute the JSONL — that's reserved for
    # real turns and explicit events.
    assert rows_after == rows_before
