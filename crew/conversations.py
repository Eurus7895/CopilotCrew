"""Bounded session continuity for chatty modes (direct + agent).

Per the harness principles in CLAUDE.md:

* **#3 Structured artifacts survive context resets.** The JSONL log under
  ``~/.crew/conversations/<scope>.jsonl`` is the source of truth — every
  turn is appended as one JSON row. The Copilot ``session_id`` is a cache
  on top of that log; if Copilot expires the session, the log persists.
* **#8 Context is scarce.** Sessions are bounded at ``CREW_TURN_CAP``
  turns (default 20). When the cap hits, ``rotate`` summarises the JSONL
  tail into ≤200 words and starts a new SDK session seeded with that
  summary. Pipelines and the evaluator never resume — they always start
  fresh per principle #2.
* **#2 Fresh context where it matters.** This module is for chatty modes
  only. ``run_pipeline`` and ``crew.evaluator.evaluate`` continue to call
  ``create_session()`` with no ``session_id`` passthrough.

Scope keys are a hash of ``(cwd, mode, agent)`` for the auto-default,
or ``("named", name)`` for explicit ``--session NAME`` threads (which are
intentionally global — a named thread can be picked up from any cwd).
The hash keeps filenames filesystem-safe; the human-readable cwd is kept
inside the ``sessions.json`` value so ``crew sessions list`` can render
it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
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
SUMMARY_INPUT_TURN_TAIL = 40  # how many recent turns feed into the summary call


@dataclass(frozen=True)
class SessionState:
    session_id: str
    turn_count: int
    cwd: str | None
    mode: str
    agent: str | None
    named: str | None
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


def _conversations_dir(crew_home: Path | None = None) -> Path:
    return _resolve_crew_home(crew_home) / "conversations"


def _jsonl_path(scope: str, crew_home: Path | None = None) -> Path:
    return _conversations_dir(crew_home) / f"{scope}.jsonl"


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
    serialised = json.dumps(entries, indent=2) + "\n"
    # Atomic write — never leave a half-written sessions.json behind.
    fd, tmp_path = tempfile.mkstemp(prefix="sessions.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialised)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def compute_scope(
    *,
    cwd: Path | str | None,
    mode: str,
    agent: str | None = None,
    named: str | None = None,
) -> str:
    """Return a deterministic, filesystem-safe scope key.

    Named sessions are global: ``--session refactor-x`` returns the same
    key regardless of cwd. The auto-default hashes ``(mode, agent, cwd)``
    so two repos can't accidentally share memory.
    """
    if named:
        digest = hashlib.sha256(f"named::{named}".encode()).hexdigest()[:8]
        return f"named__{digest}"
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
            named=entry.get("named"),
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
    named: str | None,
    started_at: str | None = None,
    crew_home: Path | None = None,
) -> SessionState:
    entries = _load_all(crew_home)
    existing = entries.get(scope, {})
    started = started_at or existing.get("started_at") or _now_iso()
    cwd_str = str(Path(cwd).resolve()) if cwd is not None else None
    last_used = _now_iso()
    entry = {
        "session_id": session_id,
        "turn_count": turn_count,
        "cwd": cwd_str,
        "mode": mode,
        "agent": agent,
        "named": named,
        "started_at": started,
        "last_used": last_used,
    }
    entries[scope] = entry
    _save_all(entries, crew_home)
    return SessionState(
        session_id=session_id,
        turn_count=turn_count,
        cwd=cwd_str,
        mode=mode,
        agent=agent,
        named=named,
        started_at=started,
        last_used=last_used,
    )


def clear_session(scope: str, crew_home: Path | None = None) -> bool:
    """Drop the sessions.json entry and the JSONL file for ``scope``.

    Returns True if anything was removed. Idempotent — clearing a missing
    scope is a no-op that returns False.
    """
    removed = False
    entries = _load_all(crew_home)
    if scope in entries:
        del entries[scope]
        _save_all(entries, crew_home)
        removed = True
    jsonl = _jsonl_path(scope, crew_home)
    if jsonl.exists():
        jsonl.unlink()
        removed = True
    return removed


def clear_all(crew_home: Path | None = None) -> int:
    entries = _load_all(crew_home)
    count = 0
    for scope in list(entries.keys()):
        if clear_session(scope, crew_home):
            count += 1
    return count


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
    """Append a non-turn event row (e.g. ``{"event": "rotated"}``).

    These rows survive in the JSONL alongside turns so the audit trail
    shows where rotations happened.
    """
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


def list_scopes(crew_home: Path | None = None) -> list[SessionState]:
    out: list[SessionState] = []
    for scope in sorted(_load_all(crew_home).keys()):
        state = load_session(scope, crew_home)
        if state is not None:
            out.append(state)
    return out


def list_scope_keys(crew_home: Path | None = None) -> list[str]:
    return sorted(_load_all(crew_home).keys())


def tail(scope: str, n: int = 20, crew_home: Path | None = None) -> list[dict[str, Any]]:
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
    if n <= 0:
        return rows
    return rows[-n:]


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
    """Return the model to use for the rotation summary call.

    Smaller / cheaper when available (per the harness principle of keeping
    expensive context-management work off the user's main model). Override
    with ``CREW_SUMMARY_MODEL``; otherwise fall back to the user's model.
    """
    override = os.environ.get("CREW_SUMMARY_MODEL")
    if override:
        return override
    return model


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
    tail_size: int = SUMMARY_INPUT_TURN_TAIL,
) -> str:
    """Compress the JSONL tail of ``scope`` into a short handoff note.

    Returns ``"(no prior context)"`` when the log is empty / missing — the
    caller can still inject it without a special-case branch.
    """
    rows = tail(scope, n=tail_size, crew_home=crew_home)
    if not rows:
        return "(no prior context)"
    body = _format_turns_for_summary(rows)
    if not body.strip():
        return "(no prior context)"
    return await _call_summary(body, model=model)


def render_session_table(states: list[SessionState]) -> str:
    """Pretty-print a list of session states for ``crew sessions list``."""
    if not states:
        return "(no sessions yet)\n"
    rows: list[tuple[str, str, str, str]] = []
    for s in states:
        if s.named:
            label = f"named:{s.named}"
            cwd_col = "(any cwd)"
        else:
            persona = f":{s.agent}" if s.agent else ""
            label = f"{s.mode}{persona}"
            cwd_col = s.cwd or "(unknown cwd)"
        turns_col = f"{s.turn_count} turn{'s' if s.turn_count != 1 else ''}"
        rows.append((label, cwd_col, turns_col, s.last_used))

    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    out_lines = []
    for r in rows:
        out_lines.append(
            f"{r[0]:<{widths[0]}}  {r[1]:<{widths[1]}}  "
            f"{r[2]:<{widths[2]}}  {r[3]}"
        )
    return "\n".join(out_lines) + "\n"


def write_table(states: list[SessionState], stream=None) -> None:
    (stream or sys.stdout).write(render_session_table(states))
