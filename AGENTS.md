# AGENTS.md — Crew session-start orientation

You are working in **Crew**, a terminal-native virtual assistant powered by
the Copilot SDK. Read `CLAUDE.md` for the full design doc.

## Project shape

- `crew/cli.py` — `crew "<prompt>"` entry point
- `crew/direct.py` — direct mode: single LLM call, no pipeline, no governance
- `crew/sdk/` — thin wrappers over the Copilot SDK
- `crew/harness/` — ported from `Eurus7895/CopilotHarness@dev`; dormant in v1
  direct mode, activated by Day 2+ pipelines
- `pipelines/` — self-contained pipeline directories (Day 2+)

## Two modes

The intent router (Day 2+) classifies every request as `direct` or
`pipeline:{name}`. Direct mode is the fast path — one Copilot SDK call, MCP
available, streamed to terminal. Pipelines are governed (generator + evaluator
+ correction loop). See CLAUDE.md "Agent Complexity Model".

## Build status

Currently on **Day 1** of the build order. Direct mode + harness port + agent
loader landed. Day 2+ tasks per CLAUDE.md "Build Order".
