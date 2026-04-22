# AGENTS.md — Crew session-start orientation

You are working in **Crew**, a terminal-native virtual assistant powered by
the Copilot SDK. Read `CLAUDE.md` for the full design doc.

## Project shape

- `crew/cli.py` — `crew "<prompt>"` entry point; dispatches via the intent
  router unless `--direct` / `--pipeline` forces a mode
- `crew/direct.py` — direct mode: single LLM call, no pipeline, no governance
- `crew/intent_router.py` — one classifier LLM call → `direct` or
  `pipeline:{name}`; falls back to direct on any failure
- `crew/pipeline_registry.py` — discovers `pipelines/*/pipeline.yaml` and
  loads the resolved `PipelineConfig`
- `crew/pipeline_runner.py` — Level 0 execution; fires lifecycle hooks
- `crew/hooks.py` — in-process hook registry (`session-start`,
  `pre-tool-use`, `post-tool-use`, `on-eval-fail`, `on-escalate`, `post-run`)
- `crew/sdk/` — thin wrappers over the Copilot SDK
- `crew/harness/` — ported from `Eurus7895/CopilotHarness@dev`; dormant in
  Level 0, activated by the Day 3+ correction loop
- `pipelines/` — self-contained pipeline directories; currently
  `pipelines/standup/` (Level 0)

## Two modes

The intent router classifies every request as `direct` or `pipeline:{name}`.
Direct mode is the fast path — one Copilot SDK call, MCP available, streamed
to terminal. Pipelines are governed (Level 0 runs a single generator with
hooks + plan JSON; Level 1+ adds an isolated evaluator on Day 3). See
CLAUDE.md "Agent Complexity Model".

## Build status

Currently on **Day 2** of the build order. Intent router, pipeline registry,
Level 0 runner, hook injection points, and the `daily-standup` pipeline have
landed. Day 3+ adds the evaluator and correction loop.
