"""`crew` CLI entry point.

The router decides between direct mode, a standalone agent, or a pipeline
for every non-flagged, non-slash invocation. ``--direct``,
``--agent NAME``, and ``--pipeline`` force the respective modes. Prompts
starting with ``/`` are parsed as slash commands and bypass the router
entirely (zero-cost deterministic dispatch).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from crew import agent_registry, intent_router, pipeline_registry, pipeline_runner
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
    """Parse ``/<name> [rest]`` and dispatch without calling the router.

    Lookup order: pipelines, then standalone agents. Unknown names exit
    with code 2 and print the available commands. Called only when the
    user typed a slash command AND did not pass an override flag.
    """
    name, _, rest = prompt[1:].partition(" ")
    name = name.strip()
    rest = rest.strip()

    if not name:
        _slash_usage_error("empty command after /")
        return

    try:
        config = pipeline_registry.load_pipeline(name)
    except pipeline_registry.PipelineNotFound:
        config = None

    if config is not None:
        route_dump = {
            "mode": "slash",
            "pipeline": config.name,
            "agent": None,
            "params": {},
            "reason": "slash command",
        }
        await pipeline_runner.run_level_0(
            config, rest, model=model, route_result=route_dump
        )
        return

    try:
        agent_cfg = agent_registry.load_agent(name)
    except agent_registry.AgentNotFound:
        agent_cfg = None

    if agent_cfg is not None:
        if not agent_cfg.standalone:
            _slash_usage_error(
                f"/{name} is a subagent-only agent and cannot be invoked directly"
            )
            return
        await run_direct(rest, model=model, agent_prompt=agent_cfg.prompt)
        return

    _slash_usage_error(f"unknown command: /{name}")


def _available_slash_commands() -> list[str]:
    pipelines = [p.name for p in pipeline_registry.discover()]
    agents = [a.name for a in agent_registry.discover() if a.standalone]
    return sorted({*pipelines, *agents})


def _slash_usage_error(msg: str) -> None:
    available = _available_slash_commands()
    sys.stderr.write(f"crew: {msg}\n")
    if available:
        sys.stderr.write("available: " + ", ".join(f"/{c}" for c in available) + "\n")
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
