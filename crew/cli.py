"""`crew` CLI entry point.

The router decides between direct mode and a pipeline for every non-flagged
invocation. ``--direct`` and ``--pipeline`` force the respective modes (per
CLAUDE.md "Execution Modes").
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from crew import intent_router, pipeline_registry, pipeline_runner
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
        help="Force direct mode (single LLM call, no pipeline).",
    )
    mode.add_argument(
        "--pipeline",
        action="store_true",
        help="Force pipeline mode (intent router picks the pipeline).",
    )
    return parser


async def _dispatch(prompt: str, *, direct: bool, pipeline: bool, model: str | None) -> None:
    if direct:
        await run_direct(prompt, model=model)
        return

    pipelines = pipeline_registry.discover()

    if pipeline:
        verdict = await intent_router.route(
            prompt, pipelines, model=model, require_pipeline=True
        )
    else:
        verdict = await intent_router.route(prompt, pipelines, model=model)

    if verdict.mode == "direct":
        await run_direct(prompt, model=model)
        return

    assert verdict.pipeline is not None  # guaranteed by intent_router
    config = pipeline_registry.load_pipeline(verdict.pipeline)
    route_dump = {
        "mode": verdict.mode,
        "pipeline": verdict.pipeline,
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
            _dispatch(prompt, direct=args.direct, pipeline=args.pipeline, model=args.model)
        )
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
