"""`crew` CLI entry point.

The router decides between direct mode, a standalone agent, or a pipeline
for every non-flagged, non-slash invocation. ``--direct``,
``--agent NAME``, and ``--pipeline`` force the respective modes. Prompts
starting with ``/`` are parsed as slash commands that invoke skills —
the skill's instructions are appended to the session's system message so
the call proceeds with the capability in-context. Slash dispatch bypasses
the intent router (zero LLM cost).

**Memory.** Direct + agent + slash modes auto-resume the per-(cwd, mode,
[agent|skill]) Copilot session up to ``CREW_TURN_CAP`` turns (default 20),
then rotate to a fresh session seeded with a one-paragraph summary
(``crew/conversations.py``). Pipelines and the evaluator are always
one-shot — no ``session_id`` passthrough, ever (per CLAUDE.md principle
#2). Override flags: ``--new`` forces fresh, ``--session NAME`` uses a
global named thread, ``--no-memory`` skips logging entirely.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from crew import (
    agent_registry,
    conversations,
    intent_router,
    pipeline_registry,
    pipeline_runner,
    skill_registry,
)
from crew.direct import DirectResult, run_direct


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crew",
        description="Crew — terminal-native virtual assistant.",
    )
    parser.add_argument("prompt", nargs="+", help="The prompt to send.")
    parser.add_argument("--model", default=None, help="Override the model.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--direct",
        action="store_true",
        help="Force direct mode (single LLM call, no pipeline, generic assistant).",
    )
    mode.add_argument(
        "--agent",
        metavar="NAME",
        default=None,
        help="Force a standalone agent persona (single LLM call, no pipeline).",
    )
    mode.add_argument(
        "--pipeline",
        action="store_true",
        help="Force pipeline mode (intent router picks the pipeline).",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="Force a fresh Copilot session for this scope (drops cached session_id).",
    )
    parser.add_argument(
        "--session",
        metavar="NAME",
        default=None,
        help="Use a named global thread instead of the per-cwd auto-scope.",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        dest="no_memory",
        help="One-shot call: do not log to ~/.crew/conversations or resume any session.",
    )
    return parser


# ── Memory wrapper ───────────────────────────────────────────────────────────


async def _run_direct_with_memory(
    prompt: str,
    *,
    model: str | None,
    mode: str,                            # "direct" | "agent" | "slash"
    agent_name: str | None,
    skill_name: str | None,
    agent_prompt: str | None,
    skill_prompt: str | None,
    new: bool,
    named: str | None,
    no_memory: bool,
) -> DirectResult | None:
    """Wrap ``run_direct`` with the conversations bookkeeping.

    ``no_memory=True`` skips the wrapper entirely — equivalent to the
    pre-Day-4-A behaviour. Pipelines and the evaluator never call this
    function; they go straight to ``CopilotClient`` with no ``session_id``.
    """
    if no_memory:
        await run_direct(
            prompt,
            model=model,
            agent_prompt=agent_prompt,
            skill_prompt=skill_prompt,
        )
        return None

    scope_agent = agent_name if mode == "agent" else (
        skill_name if mode == "slash" else None
    )
    cwd = None if named else Path.cwd()
    scope = conversations.compute_scope(
        cwd=cwd, mode=mode, agent=scope_agent, named=named
    )

    state = None if new else conversations.load_session(scope)

    history_prompt: str | None = None
    session_id: str | None = None
    next_turn_count = 1
    started_at: str | None = None

    if state is not None:
        if conversations.should_rotate(state):
            history_prompt = await conversations.summarize_for_rotation(
                scope, model=model
            )
            conversations.append_event(
                scope,
                "rotated",
                {
                    "old_session_id": state.session_id,
                    "old_turn_count": state.turn_count,
                    "summary": history_prompt,
                },
            )
            session_id = None  # fresh SDK session
            next_turn_count = 1
            started_at = state.started_at  # logically the same thread
        else:
            session_id = state.session_id
            next_turn_count = state.turn_count + 1
            started_at = state.started_at

    result = await run_direct(
        prompt,
        model=model,
        agent_prompt=agent_prompt,
        skill_prompt=skill_prompt,
        history_prompt=history_prompt,
        session_id=session_id,
    )

    conversations.append_turn(
        scope,
        mode=mode,
        agent=scope_agent,
        user=prompt,
        assistant=result.assistant_text,
        session_id=result.session_id,
    )
    conversations.save_session(
        scope,
        session_id=result.session_id,
        turn_count=next_turn_count,
        cwd=cwd,
        mode=mode,
        agent=scope_agent,
        named=named,
        started_at=started_at,
    )
    return result


# ── Slash dispatch ───────────────────────────────────────────────────────────


async def _dispatch_slash(
    prompt: str,
    *,
    model: str | None,
    new: bool,
    named: str | None,
    no_memory: bool,
) -> None:
    """Parse ``/<skill-name> [rest]`` and dispatch without calling the router.

    A slash command invokes a skill: the skill's instructions are appended
    to the session's system message, and the rest of the prompt is sent
    as the user input. Direct mode is used (no agent persona, no pipeline
    governance). Unknown skills exit with code 2 and list the available
    commands.

    ``/help`` is a built-in: it prints the local registry (pipelines,
    standalone agents, skills) without calling the SDK. The built-in
    shadows any user-defined ``skills/help/`` so help output is always
    deterministic.
    """
    name, _, rest = prompt[1:].partition(" ")
    name = name.strip()
    rest = rest.strip()

    if not name:
        _slash_usage_error("empty command after /")
        return

    if name == "help":
        _print_help()
        return

    try:
        skill = skill_registry.load_skill(name)
    except skill_registry.SkillNotFound:
        _slash_usage_error(f"unknown skill: /{name}")
        return

    await _run_direct_with_memory(
        rest,
        model=model,
        mode="slash",
        agent_name=None,
        skill_name=skill.name,
        agent_prompt=None,
        skill_prompt=skill.instructions,
        new=new,
        named=named,
        no_memory=no_memory,
    )


def _available_slash_commands() -> list[str]:
    names = {s.name for s in skill_registry.discover()}
    names.add("help")
    return sorted(names)


def _slash_usage_error(msg: str) -> None:
    available = _available_slash_commands()
    sys.stderr.write(f"crew: {msg}\n")
    sys.stderr.write(
        "available commands: " + ", ".join(f"/{c}" for c in available) + "\n"
    )
    sys.stderr.write("try `/help` to list pipelines, agents, and skills\n")
    raise SystemExit(2)


def _print_help() -> None:
    """Print discovered pipelines, standalone agents, and skills.

    Zero LLM cost — straight registry walk, written to stdout. Empty
    sections are shown explicitly so the user can tell the registry was
    actually consulted (vs. a silent failure).
    """
    pipelines = pipeline_registry.discover()
    agents = [a for a in agent_registry.discover() if a.standalone]
    skills = skill_registry.discover()

    out = sys.stdout

    out.write("Crew — what's available in this project\n")
    out.write("=" * 40 + "\n\n")

    out.write("Pipelines (governed workflows; `crew \"<intent>\"`)\n")
    if pipelines:
        for p in pipelines:
            desc = p.description or "(no description)"
            out.write(f"  {p.name} — Level {p.level} — {desc}\n")
    else:
        out.write("  (none registered — add one under pipelines/<name>/)\n")
    out.write("\n")

    out.write("Agents (persona swap; `crew --agent NAME` or auto-summoned)\n")
    if agents:
        for a in agents:
            desc = a.description or "(no description)"
            out.write(f"  {a.name} — {desc}\n")
    else:
        out.write("  (none registered — add one under agents/<name>.md)\n")
    out.write("\n")

    out.write("Skills (capability injection; `/<skill-name> <args>`)\n")
    if skills:
        for s in skills:
            desc = s.description or "(no description)"
            out.write(f"  /{s.name} — {desc}\n")
    else:
        out.write("  (none registered — add one under skills/<name>/SKILL.md)\n")
    out.write("\n")

    out.write("Other modes:\n")
    out.write("  crew \"<prompt>\"          → router picks direct / agent / pipeline\n")
    out.write("  crew --direct \"<prompt>\" → force direct mode (single LLM call)\n")
    out.write("  crew --pipeline \"<x>\"    → force pipeline mode\n")
    out.write("  /help                    → this listing (zero LLM cost)\n")
    out.write("\n")
    out.write("Memory:\n")
    out.write("  --new                    → fresh session for this scope\n")
    out.write("  --session NAME           → named thread (cwd-independent)\n")
    out.write("  --no-memory              → one-shot, no log, no resume\n")
    out.write("  crew sessions list       → inspect saved sessions\n")
    out.flush()


# ── Main dispatcher ──────────────────────────────────────────────────────────


async def _dispatch(
    prompt: str,
    *,
    direct: bool,
    agent: str | None,
    pipeline: bool,
    model: str | None,
    new: bool,
    named: str | None,
    no_memory: bool,
) -> None:
    if direct:
        await _run_direct_with_memory(
            prompt,
            model=model,
            mode="direct",
            agent_name=None,
            skill_name=None,
            agent_prompt=None,
            skill_prompt=None,
            new=new,
            named=named,
            no_memory=no_memory,
        )
        return

    if agent is not None:
        agent_cfg = agent_registry.load_agent(agent)
        await _run_direct_with_memory(
            prompt,
            model=model,
            mode="agent",
            agent_name=agent,
            skill_name=None,
            agent_prompt=agent_cfg.prompt,
            skill_prompt=None,
            new=new,
            named=named,
            no_memory=no_memory,
        )
        return

    # Slash commands short-circuit the router when no override flag was
    # passed. Explicit overrides above take precedence so the user can
    # send a literal prompt starting with "/" via `--direct "/foo"`.
    if not pipeline and prompt.startswith("/"):
        await _dispatch_slash(
            prompt, model=model, new=new, named=named, no_memory=no_memory
        )
        return

    pipelines = pipeline_registry.discover()
    agents = agent_registry.discover()

    if pipeline:
        verdict = await intent_router.route(
            prompt, pipelines, agents, model=model, require_pipeline=True
        )
    else:
        verdict = await intent_router.route(prompt, pipelines, agents, model=model)

    if verdict.mode == "direct":
        await _run_direct_with_memory(
            prompt,
            model=model,
            mode="direct",
            agent_name=None,
            skill_name=None,
            agent_prompt=None,
            skill_prompt=None,
            new=new,
            named=named,
            no_memory=no_memory,
        )
        return

    if verdict.mode == "agent":
        assert verdict.agent is not None
        agent_cfg = agent_registry.load_agent(verdict.agent)
        await _run_direct_with_memory(
            prompt,
            model=model,
            mode="agent",
            agent_name=verdict.agent,
            skill_name=None,
            agent_prompt=agent_cfg.prompt,
            skill_prompt=None,
            new=new,
            named=named,
            no_memory=no_memory,
        )
        return

    assert verdict.pipeline is not None  # guaranteed by intent_router
    config = pipeline_registry.load_pipeline(verdict.pipeline)
    route_dump = {
        "mode": verdict.mode,
        "pipeline": verdict.pipeline,
        "agent": verdict.agent,
        "params": verdict.params,
        "reason": verdict.reason,
    }
    # Pipelines stay one-shot per CLAUDE.md principle #2 — no session_id
    # passthrough, no conversations bookkeeping. The pipeline's own plan
    # JSON under ~/.crew/plans/ is the audit trail for governed workflows.
    await pipeline_runner.run_pipeline(
        config, prompt, verdict.params, model=model, route_result=route_dump
    )


# ── `crew sessions` subcommand ───────────────────────────────────────────────


def _resolve_scope_or_die(user_input: str) -> str:
    keys = conversations.list_scope_keys()
    if user_input in keys:
        return user_input
    # Try interpreting as a named session.
    named = conversations.compute_scope(
        cwd=None, mode="direct", agent=None, named=user_input
    )
    if named in keys:
        return named
    # Substring match (single hit only).
    matches = [k for k in keys if user_input in k]
    if len(matches) == 1:
        return matches[0]
    if matches:
        sys.stderr.write(
            f"crew: ambiguous scope {user_input!r}; matches: {', '.join(matches)}\n"
        )
    else:
        sys.stderr.write(f"crew: no scope matches {user_input!r}\n")
    raise SystemExit(2)


def _sessions_main(args: list[str]) -> int:
    if not args or args[0] in ("list", "ls"):
        states = conversations.list_scopes()
        sys.stdout.write(conversations.render_session_table(states))
        return 0
    if args[0] == "show":
        if len(args) < 2:
            sys.stderr.write("usage: crew sessions show <scope-or-name>\n")
            return 2
        scope = _resolve_scope_or_die(args[1])
        rows = conversations.tail(scope, n=20)
        if not rows:
            sys.stdout.write("(no rows)\n")
            return 0
        for row in rows:
            sys.stdout.write(json.dumps(row) + "\n")
        return 0
    if args[0] == "clear":
        if len(args) >= 2 and args[1] == "--all":
            count = conversations.clear_all()
            sys.stdout.write(f"cleared {count} session(s)\n")
            return 0
        if len(args) < 2:
            sys.stderr.write("usage: crew sessions clear <scope-or-name> | --all\n")
            return 2
        scope = _resolve_scope_or_die(args[1])
        ok = conversations.clear_session(scope)
        sys.stdout.write(("cleared " if ok else "no such scope: ") + scope + "\n")
        return 0
    sys.stderr.write(
        f"crew: unknown sessions command {args[0]!r}; try `list`, `show`, or `clear`\n"
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "sessions":
        return _sessions_main(raw[1:])
    args = build_parser().parse_args(raw)
    prompt = " ".join(args.prompt)
    try:
        asyncio.run(
            _dispatch(
                prompt,
                direct=args.direct,
                agent=args.agent,
                pipeline=args.pipeline,
                model=args.model,
                new=args.new,
                named=args.session,
                no_memory=args.no_memory,
            )
        )
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
