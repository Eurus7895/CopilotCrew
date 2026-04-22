"""`crew` CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys

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
        help="Force pipeline mode (Day 2+).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.pipeline:
        sys.stderr.write(
            "--pipeline is not implemented until Day 2 (intent router).\n"
        )
        return 2

    prompt = " ".join(args.prompt)
    asyncio.run(run_direct(prompt, model=args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
