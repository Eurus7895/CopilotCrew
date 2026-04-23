"""`crew` CLI entry point.

The router decides between direct mode, a standalone agent, or a pipeline
for every non-flagged, non-slash invocation. ``--direct``,
``--agent NAME``, and ``--pipeline`` force the respective modes. Prompts
starting with ``/`` are parsed as slash commands that invoke skills —
the skill's instructions are appended to the session's system message so
the call proceeds with the capability in-context. Slash dispatch bypasses
the intent router (zero LLM cost).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from crew import (
    agent_registry,
    intent_router,
    pipeline_registry,
    pipeline_runner,
    skill_registry,
)
from crew.direct import run_direct


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
    return parser


async def _dispatch_slash(prompt: str, *, model: str | None) -> None:
    """Parse ``/<skill-name> [rest]`` and dispatch without calling the router.

    A slash command invokes a skill: the skill's instructions are appended
    to the session's system message, and the rest of the prompt is sent
    as the user input. Direct mode is used (no agent persona, no pipeline
    governance). Unknown skills exit with code 2 and list the available
    commands.
    """
    name, _, rest = prompt[1:].partition(" ")
    name = name.strip()
    rest = rest.strip()

    if not name:
        _slash_usage_error("empty command after /")
        return

    try:
        skill = skill_registry.load_skill(name)
    except skill_registry.SkillNotFound:
        _slash_usage_error(f"unknown skill: /{name}")
        return

    await run_direct(rest, model=model, skill_prompt=skill.instructions)


def _available_slash_commands() -> list[str]:
    return sorted(s.name for s in skill_registry.discover())


def _slash_usage_error(msg: str) -> None:
    available = _available_slash_commands()
    sys.stderr.write(f"crew: {msg}\n")
    if available:
        sys.stderr.write(
            "available skills: " + ", ".join(f"/{c}" for c in available) + "\n"
        )
    else:
        sys.stderr.write("no skills registered (add one under skills/<name>/SKILL.md)\n")
    raise SystemExit(2)


async def _dispatch(
    prompt: str,
    *,
    direct: bool,
    agent: str | None,
    pipeline: bool,
    model: str | None,
) -> None:
    if direct:
        await run_direct(prompt, model=model)
        return

    if agent is not None:
        agent_cfg = agent_registry.load_agent(agent)
        await run_direct(prompt, model=model, agent_prompt=agent_cfg.prompt)
        return

    # Slash commands short-circuit the router when no override flag was
    # passed. Explicit overrides above take precedence so the user can
    # send a literal prompt starting with "/" via `--direct "/foo"`.
    if not pipeline and prompt.startswith("/"):
        await _dispatch_slash(prompt, model=model)
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
        await run_direct(prompt, model=model)
        return

    if verdict.mode == "agent":
        assert verdict.agent is not None
        agent_cfg = agent_registry.load_agent(verdict.agent)
        await run_direct(prompt, model=model, agent_prompt=agent_cfg.prompt)
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
    await pipeline_runner.run_level_0(
        config, prompt, verdict.params, model=model, route_result=route_dump
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompt = " ".join(args.prompt)
    try:
        asyncio.run(
            _dispatch(
                prompt,
                direct=args.direct,
                agent=args.agent,
                pipeline=args.pipeline,
                model=args.model,
            )
        )
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
