# AGENTS.md — Crew session-start orientation

You are working in **Crew**, a terminal-native virtual assistant powered by
the Copilot SDK. Read `CLAUDE.md` for the full design doc.

## Project shape

- `crew/cli.py` — `crew "<prompt>"` entry point. Prompts starting with `/`
  are skill invocations (zero-cost dispatch); otherwise the intent router
  runs unless `--direct` / `--agent NAME` / `--pipeline` forces a mode.
  Direct + agent + slash modes auto-resume their per-(cwd, mode, [agent|skill])
  Copilot session via `crew/conversations.py`; `--new` starts fresh
- `crew/conversations.py` — bounded session continuity for chatty modes:
  per-scope `session_id` cache in `~/.crew/sessions.json`, silent
  summary-rotation when turn count hits `CREW_TURN_CAP` (default 20).
  Pipelines + the evaluator never call this module — they stay one-shot
  per principle #2
- `crew/direct.py` — direct mode: single LLM call, no pipeline, no
  governance. Accepts an optional `agent_prompt` to swap the system message
  for a standalone-agent persona
- `crew/intent_router.py` — one classifier LLM call → `direct`,
  `agent:{name}`, or `pipeline:{name}`; falls back to direct on any failure
- `crew/agent_registry.py` — discovers `agents/*.md` files and loads the
  resolved `AgentConfig` (shared by standalone + subagent callers)
- `crew/pipeline_registry.py` — discovers `pipelines/*/pipeline.yaml` and
  loads the resolved `PipelineConfig`
- `crew/skill_registry.py` — discovers `skills/<name>/SKILL.md` bundles
  (instructions + optional `scripts/` and `references/`). Skills are
  invoked by slash commands and appended to the session's system message
- `crew/pipeline_runner.py` — Level 0 + Level 1 execution; `run_pipeline`
  dispatches by `config.level`. Fires lifecycle hooks (including
  `on-eval-fail` / `on-escalate` for Level 1)
- `crew/evaluator.py` — isolated evaluator session for Level 1 pipelines.
  Fresh `CopilotClient`, no MCP, no tools — receives only the generator
  output text + the pipeline's schema/criteria. Returns a strict JSON
  verdict (`status`, `issues`, `summary`) parsed defensively
- `crew/hooks.py` — in-process hook registry (`session-start`,
  `pre-tool-use`, `post-tool-use`, `on-eval-fail`, `on-escalate`, `post-run`)
- `crew/sdk/` — thin wrappers over the Copilot SDK
- `crew/harness/` — ported from `Eurus7895/CopilotHarness@dev`. The
  Day 3 Level 1 loop is Copilot-SDK-native inside `pipeline_runner`;
  the SQLite-stage modules (`correction_loop.py`, `state.py`, …) remain
  dormant until a future workflow needs cross-stage state
- `agents/` — flat directory of standalone / subagent-capable persona
  files. One `.md` per agent (e.g. `agents/coder.md`)
- `skills/` — directory of skill bundles. Each skill is
  `skills/<name>/SKILL.md` plus optional `references/` and `scripts/`
  subdirectories. Currently: `skills/debug/`
- `pipelines/` — self-contained pipeline directories;
  `pipelines/standup/` (Level 0) and `pipelines/incident-triage/`
  (Level 1, generator + evaluator + correction loop)
- `crew/gui/` — optional local web dashboard (`[gui]` extra), launched
  via `crew gui`. FastAPI + Jinja2 + HTMX + vanilla CSS, no build step.
  Routes under `crew/gui/routes/`, bridge logic in `crew/gui/services/`
  (`pinned`, `mocks`, `standup_service`, `status_service`, `editor`,
  `events_bus`, `bootstrap`). Pinned rail and the standup card are live
  over real registries + `~/.crew/outputs/daily-standup/`; timeline,
  facts, PR/Slack cards, and working-on chips read JSONL stubs seeded
  into `~/.crew/gui/` and `~/.crew/memory.jsonl`. Pipeline invocation
  reuses `pipeline_runner.run_pipeline` with stdout redirected into an
  SSE pub/sub; a module lock blocks concurrent runs. Copilot SDK imports
  inside `standup_service` are lazy so the GUI boots even without the
  SDK for read-only use

## Three modes + skill invocation

The intent router classifies every non-slash, non-flagged request as
`direct`, `agent:{name}`, or `pipeline:{name}`.

- **Direct** — one Copilot SDK call with a generic assistant prompt, MCP
  available, streamed to terminal. No output file.
- **Agent** — one Copilot SDK call with a persona's prompt (`agents/*.md`).
  Like direct mode, but with a specialised system message. No output file.
- **Pipeline** — governed workflow. Level 0 runs a single generator with
  hooks + plan JSON; Level 1 adds an isolated evaluator session
  (`crew/evaluator.py`) and a correction loop with up to 3 attempts
  before escalation. Level 2+ is gated on observed Level 1 failures and
  is not in v1.

**Slash commands** (`/<skill-name>`) invoke a skill. The skill's
instructions are appended to the session's system message so the call
proceeds with the capability in-context. Slash dispatch bypasses the
intent router (zero LLM cost) and uses direct mode underneath. Override
flags (`--direct`, `--agent`, `--pipeline`) take precedence over slash
parsing. `/help` is a built-in that prints the local registry without
calling the SDK.

**Memory.** Direct, agent, and slash modes auto-resume the
per-(cwd, mode, [agent|skill]) Copilot session up to `CREW_TURN_CAP`
turns (default 20), then silently rotate to a fresh session seeded with
a one-paragraph summary of the prior conversation. `--new` forces a
fresh start. Pipelines and the evaluator are **always** one-shot — no
`session_id` passthrough, ever.

**Plugins** (Phase 2+, not implemented yet) will bundle multiple skills —
and optionally agents, pipelines, and hooks — into a single installable
directory. A future `crew install <name>@<repo>` command will copy the
bundle's directory into the project; the skill registry already supports
multiple search roots, so `plugins/<plugin-name>/skills/` will be picked
up automatically once the install command lands.

See CLAUDE.md "Agent Complexity Model" and "Phase 5 — Plugin Marketplace".

## Build status

**Day 4-A shipped, plus the web GUI (Phase 7) ahead of schedule.**
Bounded session continuity for chatty modes: `crew/conversations.py`
persists the per-scope Copilot `session_id` in `~/.crew/sessions.json`
and appends every turn to a rotation-input log; once `CREW_TURN_CAP` is
hit, the next call silently summarises the tail (via
`CREW_SUMMARY_MODEL` when set, else the user's model), starts a fresh
SDK session seeded with the summary, and marks the rotation in the log.
One user-facing flag: `--new` to force fresh. Pipelines + the evaluator
stay one-shot — guarded by runtime tests asserting no `session_id` is
ever passed to `create_session` from the runner.

The GUI landed alongside Day 4-A: `crew gui` launches a three-pane
FastAPI dashboard (left rail pinned items + day timeline, center
cards + standup draft, right rail memory/facts). Read-only viewer
plus a launcher for the daily-standup pipeline — no new pipelines,
no new backend concepts. CLI remains primary.

Earlier days, in order: Day 2 (pipeline runner + hooks +
`daily-standup`), Day 2.5 (3-way router + `agents/` directory), Day 2.8
(slash commands invoke skills; `skills/debug/`), Day 3 (Level 1 pipelines
with isolated evaluator + correction loop; `incident-triage`), `/help`
(zero-LLM registry listing). Day 4-B+ will add the streamer + remaining
pipelines (ticket-refinement, code-review-routing, release-notes) and
subagent spawning.
