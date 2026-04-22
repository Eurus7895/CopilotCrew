"""`crew` CLI entry point.

The router decides between direct mode, a standalone agent, or a pipeline
for every non-flagged invocation. ``--direct``, ``--agent NAME``, and
``--pipeline`` force the respective modes (per CLAUDE.md "Execution Modes").
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
