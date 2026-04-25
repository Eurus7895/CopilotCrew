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
  `on-eval-fail` / `on-escalate` for Level 1). Accepts `stream_mode`
  (`verbose` / `summary`) — `crew --pipeline --summary "…"` swaps
  token-by-token streaming for terse status lines
- `crew/evaluator.py` — isolated evaluator session for Level 1 pipelines.
  Fresh `CopilotClient`, no MCP, no tools — receives only the generator
  output text + the pipeline's schema/criteria. Returns a strict JSON
  verdict (`status`, `issues`, `summary`) parsed defensively
- `crew/streamer.py` — single `on_event` handler for every Copilot
  session in Crew. Three modes: `verbose` (stream to stdout),
  `summary` (terse status lines), `silent` (capture-only, used by the
  evaluator + router). Tool-execution events fan out to optional
  callbacks so the pipeline runner keeps firing `pre-tool-use` /
  `post-tool-use` hooks without re-implementing the dispatch
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
- `pipelines/` — self-contained pipeline directories. v1 ships five:
  `standup/` and `release-notes/` (Level 0); `incident-triage/`,
  `ticket-refinement/`, and `code-review-routing/` (Level 1, each with
  generator + evaluator + schema for the correction loop)

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

**Day 4-B pipelines shipped.** All five v1 pipelines are now in
`pipelines/`: `standup` and `release-notes` (Level 0); `incident-triage`,
`ticket-refinement`, and `code-review-routing` (Level 1 with isolated
evaluator + correction loop). Each Level 1 pipeline has a JSON schema
under `schemas/` that the evaluator grades against. The intent router
discovers them automatically — no registry edits needed.

**Day 4-B streamer shipped.** `crew/streamer.py` consolidates the
previously-duplicated `on_event` handler into one `Streamer` class with
three modes (`verbose` / `summary` / `silent`). `crew --pipeline
--summary "…"` replaces token-by-token streaming with terse status
lines (generator start, per-tool call, final char count) for cron / CI /
log-file invocations — the pipeline's output file is identical either
way.

**Day 4-A shipped.** Bounded session continuity for chatty modes:
`crew/conversations.py` persists the per-scope Copilot `session_id` in
`~/.crew/sessions.json` and appends every turn to a rotation-input log;
once `CREW_TURN_CAP` is hit, the next call silently summarises the tail
(via `CREW_SUMMARY_MODEL` when set, else the user's model), starts a
fresh SDK session seeded with the summary, and marks the rotation in
the log. One user-facing flag: `--new` to force fresh. Pipelines + the
evaluator stay one-shot — guarded by runtime tests asserting no
`session_id` is ever passed to `create_session` from the runner.

Earlier days, in order: Day 2 (pipeline runner + hooks +
`daily-standup`), Day 2.5 (3-way router + `agents/` directory), Day 2.8
(slash commands invoke skills; `skills/debug/`), Day 3 (Level 1 pipelines
with isolated evaluator + correction loop; `incident-triage`), `/help`
(zero-LLM registry listing). Day 4-B's remaining open item is the
end-to-end shakedown of all five pipelines on real team data — that
needs live MCP credentials + a real repo and folds naturally into the
Day 5 first-team-member rollout.
