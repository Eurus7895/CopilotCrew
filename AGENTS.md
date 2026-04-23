# AGENTS.md — Crew session-start orientation

You are working in **Crew**, a terminal-native virtual assistant powered by
the Copilot SDK. Read `CLAUDE.md` for the full design doc.

## Project shape

- `crew/cli.py` — `crew "<prompt>"` entry point. Prompts starting with `/`
  are slash commands (zero-cost dispatch); otherwise the intent router
  runs unless `--direct` / `--agent NAME` / `--pipeline` forces a mode
- `crew/direct.py` — direct mode: single LLM call, no pipeline, no
  governance. Accepts an optional `agent_prompt` to swap the system message
  for a standalone-agent persona
- `crew/intent_router.py` — one classifier LLM call → `direct`,
  `agent:{name}`, or `pipeline:{name}`; falls back to direct on any failure
- `crew/agent_registry.py` — discovers `agents/*.md` files and loads the
  resolved `AgentConfig` (shared by standalone + subagent callers)
- `crew/pipeline_registry.py` — discovers `pipelines/*/pipeline.yaml` and
  loads the resolved `PipelineConfig`
- `crew/pipeline_runner.py` — Level 0 execution; fires lifecycle hooks
- `crew/hooks.py` — in-process hook registry (`session-start`,
  `pre-tool-use`, `post-tool-use`, `on-eval-fail`, `on-escalate`, `post-run`)
- `crew/sdk/` — thin wrappers over the Copilot SDK
- `crew/harness/` — ported from `Eurus7895/CopilotHarness@dev`; dormant in
  Level 0, activated by the Day 3+ correction loop
- `agents/` — flat directory of standalone / subagent-capable persona
  files. One `.md` per agent (e.g. `agents/coder.md`)
- `pipelines/` — self-contained pipeline directories; currently
  `pipelines/standup/` (Level 0)

## Three modes + one fast path

The intent router classifies every non-slash, non-flagged request as
`direct`, `agent:{name}`, or `pipeline:{name}`.

- **Direct** — one Copilot SDK call with a generic assistant prompt, MCP
  available, streamed to terminal. No output file.
- **Agent** — one Copilot SDK call with a persona's prompt (`agents/*.md`).
  Like direct mode, but with a specialised system message. No output file.
- **Pipeline** — governed workflow. Level 0 runs a single generator with
  hooks + plan JSON; Level 1+ adds an isolated evaluator on Day 3.

**Slash commands** (`/<name>`) bypass the router entirely and dispatch
directly to the matching pipeline or standalone agent — zero LLM cost.
Override flags (`--direct`, `--agent`, `--pipeline`) take precedence over
slash parsing.

See CLAUDE.md "Agent Complexity Model".

## Build status

Currently on **Day 2.75** of the build order. Slash commands landed on top
of Day 2.5 (3-way router + `agents/` directory) and Day 2 (pipeline runner
+ hooks + `daily-standup`). Day 3+ adds the evaluator, correction loop,
and subagent spawning.
