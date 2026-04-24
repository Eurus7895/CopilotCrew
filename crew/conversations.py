"""Bounded session continuity for chatty modes (direct + agent + slash).

Minimal by design: auto-resume the per-(cwd, mode, [agent|skill]) Copilot
session up to ``CREW_TURN_CAP`` turns, then rotate silently — summarise
the prior turns, start a fresh SDK session seeded with the summary.
Users get a continuous conversation without session-management overhead;
``--new`` at the CLI forces a fresh start.

Pipelines and the evaluator never call this module — they always start
with no ``session_id`` per CLAUDE.md principle #2.

Storage (all under ``~/.crew/``):

* ``sessions.json`` — map of scope → {session_id, turn_count, started_at, last_used}.
* ``conversations/<scope>.jsonl`` — append-only turn log; used as input
  to the rotation summary. Not exposed via the CLI — it's plumbing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from copilot import CopilotClient
from copilot.generated.session_events import SessionEvent, SessionEventType

_log = logging.getLogger("crew.conversations")


def _turn_cap_default() -> int:
    raw = os.environ.get("CREW_TURN_CAP")
    if not raw:
        return 20
    try:
        return max(1, int(raw))
    except ValueError:
        _log.warning("invalid CREW_TURN_CAP=%r; falling back to 20", raw)
        return 20


CAP = _turn_cap_default()
SUMMARY_MAX_WORDS = 200
SUMMARY_INPUT_TURN_TAIL = 40


@dataclass(frozen=True)
class SessionState:
    session_id: str
    turn_count: int
    cwd: str | None
    mode: str
    agent: str | None
    started_at: str
    last_used: str


def _resolve_crew_home(crew_home: Path | None = None) -> Path:
    if crew_home is not None:
        return Path(crew_home)
    env = os.environ.get("CREW_HOME")
    if env:
        return Path(env)
    return Path.home() / ".crew"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sessions_path(crew_home: Path | None = None) -> Path:
    return _resolve_crew_home(crew_home) / "sessions.json"


def _jsonl_path(scope: str, crew_home: Path | None = None) -> Path:
    return _resolve_crew_home(crew_home) / "conversations" / f"{scope}.jsonl"


def _load_all(crew_home: Path | None = None) -> dict[str, dict[str, Any]]:
    path = _sessions_path(crew_home)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _log.warning("could not read %s (%s); treating as empty", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_all(entries: dict[str, dict[str, Any]], crew_home: Path | None = None) -> None:
    path = _sessions_path(crew_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def compute_scope(
    *, cwd: Path | str | None, mode: str, agent: str | None = None
) -> str:
    """Return a deterministic, filesystem-safe scope key.

    ``(mode, agent, cwd)`` is hashed so filenames stay short. The full
    readable cwd is stored inside the session value, not in the key.
    """
    cwd_str = str(Path(cwd).resolve()) if cwd is not None else "<no-cwd>"
    raw = f"{mode}::{agent or ''}::{cwd_str}".encode()
    digest = hashlib.sha256(raw).hexdigest()[:8]
    agent_part = agent or "_"
    return f"{mode}__{agent_part}__{digest}"


def load_session(scope: str, crew_home: Path | None = None) -> SessionState | None:
    entry = _load_all(crew_home).get(scope)
    if not entry:
        return None
    try:
        return SessionState(
            session_id=str(entry["session_id"]),
            turn_count=int(entry.get("turn_count", 0)),
            cwd=entry.get("cwd"),
            mode=str(entry.get("mode", "direct")),
            agent=entry.get("agent"),
            started_at=str(entry.get("started_at") or _now_iso()),
            last_used=str(entry.get("last_used") or _now_iso()),
        )
    except (KeyError, ValueError, TypeError) as exc:
        _log.warning("malformed session entry for scope %s: %s", scope, exc)
        return None


def save_session(
    scope: str,
    *,
    session_id: str,
    turn_count: int,
    cwd: Path | str | None,
    mode: str,
    agent: str | None,
    started_at: str | None = None,
    crew_home: Path | None = None,
) -> SessionState:
    entries = _load_all(crew_home)
    existing = entries.get(scope, {})
    started = started_at or existing.get("started_at") or _now_iso()
    cwd_str = str(Path(cwd).resolve()) if cwd is not None else None
    last_used = _now_iso()
    entries[scope] = {
        "session_id": session_id,
        "turn_count": turn_count,
        "cwd": cwd_str,
        "mode": mode,
        "agent": agent,
        "started_at": started,
        "last_used": last_used,
    }
    _save_all(entries, crew_home)
    return SessionState(
        session_id=session_id,
        turn_count=turn_count,
        cwd=cwd_str,
        mode=mode,
        agent=agent,
        started_at=started,
        last_used=last_used,
    )


def append_turn(
    scope: str,
    *,
    mode: str,
    agent: str | None,
    user: str,
    assistant: str,
    session_id: str,
    crew_home: Path | None = None,
) -> None:
    path = _jsonl_path(scope, crew_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": _now_iso(),
        "type": "turn",
        "mode": mode,
        "agent": agent,
        "user": user,
        "assistant": assistant,
        "session_id": session_id,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def append_event(
    scope: str,
    event: str,
    payload: dict[str, Any] | None = None,
    *,
    crew_home: Path | None = None,
) -> None:
    path = _jsonl_path(scope, crew_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now_iso(), "type": "event", "event": event}
    if payload:
        row.update(payload)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def should_rotate(state: SessionState | None, *, cap: int | None = None) -> bool:
    if state is None:
        return False
    limit = cap if cap is not None else CAP
    return state.turn_count >= limit


def _read_tail(
    scope: str, n: int = SUMMARY_INPUT_TURN_TAIL, crew_home: Path | None = None
) -> list[dict[str, Any]]:
    path = _jsonl_path(scope, crew_home)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-n:] if n > 0 else rows


def _format_turns_for_summary(rows: Iterable[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in rows:
        if row.get("type") == "event":
            lines.append(f"[event] {row.get('event')}")
            continue
        user = (row.get("user") or "").strip()
        assistant = (row.get("assistant") or "").strip()
        lines.append(f"USER: {user}")
        lines.append(f"ASSISTANT: {assistant}")
    return "\n".join(lines)


_SUMMARY_SYSTEM_PROMPT = (
    "You compress prior chat history into a tight handoff note for a fresh "
    "session. Plain Markdown. No prose framing. Cover, in this order: "
    "(1) the user's overall goal, (2) decisions already made, "
    "(3) open questions or next steps, (4) key file paths or identifiers "
    "mentioned. Stay under "
    f"{SUMMARY_MAX_WORDS} words. If there is no useful history, return the "
    "single line `(no prior context)`."
)


def _resolve_summary_model(model: str | None) -> str | None:
    override = os.environ.get("CREW_SUMMARY_MODEL")
    return override or model


async def _call_summary(prompt: str, *, model: str | None) -> str:
    buffer: list[str] = []

    def on_event(event: SessionEvent) -> None:
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            delta = getattr(event.data, "delta_content", None)
            if delta:
                buffer.append(delta)

    async with CopilotClient() as client:
        async with await client.create_session(
            model=_resolve_summary_model(model),
            streaming=True,
            enable_config_discovery=False,
            system_message={"mode": "replace", "content": _SUMMARY_SYSTEM_PROMPT},
        ) as session:
            session.on(on_event)
            await session.send_and_wait(prompt)
    return "".join(buffer).strip()


async def summarize_for_rotation(
    scope: str,
    *,
    model: str | None = None,
    crew_home: Path | None = None,
) -> str:
    """Compress the JSONL tail of ``scope`` into a short handoff note.

    Returns ``"(no prior context)"`` when the log is empty / missing so
    the caller can inject it unconditionally without a special case.
    """
    rows = _read_tail(scope, crew_home=crew_home)
    if not rows:
        return "(no prior context)"
    body = _format_turns_for_summary(rows)
    if not body.strip():
        return "(no prior context)"
    return await _call_summary(body, model=model)
