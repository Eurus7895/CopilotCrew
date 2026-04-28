# AGENTS.md — Crew session-start orientation

You are working in **Crew**, a terminal-native virtual assistant powered
by the Copilot SDK. Read `CLAUDE.md` for operational rules + invariants;
`docs/ARCHITECTURE.md` for how it works; `docs/API.md` for hook + MCP
schemas; `CHANGELOG.md` for completed work; `ROADMAP.md` for what's next.

## Project shape

Top level:

- `crew/` — runtime (CLI, router, modes, hooks, streamer, SDK wrappers)
- `agents/` — flat directory of `.md` persona files (e.g. `coder.md`)
- `skills/` — `<name>/SKILL.md` bundles plus optional `references/`,
  `scripts/`. Currently: `skills/debug/`
- `pipelines/` — self-contained pipeline directories. v1 ships five:
  `standup/`, `release-notes/` (Level 0); `incident-triage/`,
  `ticket-refinement/`, `code-review-routing/` (Level 1, each with
  generator + evaluator + schema for the correction loop)
- `tests/`, `packaging/`, `docs/`

Inside `crew/`:

- `cli.py` — `crew "<prompt>"` entry. `/`-prefixed prompts are skill
  invocations (zero-cost dispatch); otherwise the intent router runs
  unless `--direct` / `--agent NAME` / `--pipeline` forces a mode.
  Direct + agent + slash modes auto-resume per
  `(cwd, mode, [agent|skill])` via `conversations.py`; `--new` resets.
- `conversations.py` — bounded session continuity for chatty modes:
  per-scope `session_id` cache in `~/.crew/sessions.json`, silent
  summary-rotation at `CREW_TURN_CAP` turns (default 20). Pipelines +
  evaluator never call this — they stay one-shot per principle #2.
- `direct.py` — direct mode: single LLM call, no pipeline, no
  governance. Optional `agent_prompt` swaps the system message for a
  standalone-agent persona.
- `intent_router.py` — one classifier LLM call → `direct`,
  `agent:{name}`, or `pipeline:{name}`; falls back to direct on failure.
- `agent_registry.py`, `pipeline_registry.py`, `skill_registry.py` —
  file-driven discovery for `agents/`, `pipelines/`, `skills/`.
- `pipeline_runner.py` — Level 0 + Level 1 execution; `run_pipeline`
  dispatches by `config.level`. Fires lifecycle hooks (including
  `on-eval-fail` / `on-escalate` for Level 1). Accepts `stream_mode`
  (`verbose` / `summary`) — `crew --pipeline --summary "…"` swaps
  token-by-token streaming for terse status lines.
- `evaluator.py` — isolated evaluator session for Level 1: fresh
  `CopilotClient`, no MCP, no tools, receives only generator output +
  schema. Returns a strict JSON verdict parsed defensively.
- `streamer.py` — single `on_event` handler for every Copilot session.
  Three modes: `verbose` (stdout), `summary` (status lines), `silent`
  (capture-only — evaluator + router). Tool-execution events fan out
  to optional callbacks so the runner keeps firing `pre-tool-use` /
  `post-tool-use` hooks.
- `hooks.py` — in-process registry: `session-start`, `pre-tool-use`,
  `post-tool-use`, `on-eval-fail`, `on-escalate`, `post-run`.
- `sdk/` — thin wrappers over the Copilot SDK.
- `harness/` — ported from `Eurus7895/CopilotHarness@dev`. The Day 3
  Level 1 loop is Copilot-SDK-native inside `pipeline_runner`; the
  SQLite-stage modules (`correction_loop.py`, `state.py`, …) remain
  dormant until a future workflow needs cross-stage state.
- `gui/` — optional desktop GUI (`[gui]` extra). FastAPI + Jinja2 +
  HTMX + vanilla CSS inside a PyWebView native window. `__main__.py`
  is the PyInstaller bundle entrypoint; `server.py` runs uvicorn on
  an ephemeral localhost port and opens the window. Three swappable
  design languages live under `templates/themes/{warm,terminal,modernist}/`
  + matching `static/themes/<name>.css`. Bridge logic in `services/`
  (`chat_service`, `pinned`, `pinned_actions`, `mocks`,
  `standup_service`, `status_service`, `editor`, `events_bus`,
  `bootstrap`). Chat reuses `crew.direct.run_direct` via a
  `CallbackStreamer`; pipeline invocation reuses
  `pipeline_runner.run_pipeline` (a module lock blocks concurrent
  runs). Copilot SDK imports inside `chat_service` and
  `standup_service` are lazy so the GUI boots without the SDK for
  read-only use.

## Three modes + skill invocation

The intent router classifies every non-slash, non-flagged request as
`direct`, `agent:{name}`, or `pipeline:{name}`.

- **Direct** — one Copilot SDK call with a generic assistant prompt,
  MCP available, streamed to terminal. No output file.
- **Agent** — one Copilot SDK call with a persona's prompt
  (`agents/*.md`). Like direct mode, but with a specialised system
  message. No output file.
- **Pipeline** — governed workflow. Level 0 runs a single generator
  with hooks + plan JSON; Level 1 adds an isolated evaluator session
  (`crew/evaluator.py`) and a correction loop with up to 3 attempts
  before escalation. Level 2+ is gated on observed Level 1 failures
  and is not in v1.

**Slash commands** (`/<skill-name>`) invoke a skill. Instructions are
appended to the session's system message; dispatch bypasses the intent
router (zero LLM cost) and uses direct mode underneath. Override flags
take precedence over slash parsing. `/help` is a built-in that prints
the local registry without calling the SDK.

**Memory.** Direct, agent, and slash modes auto-resume the
per-`(cwd, mode, [agent|skill])` Copilot session up to `CREW_TURN_CAP`
turns (default 20), then silently rotate to a fresh session seeded
with a one-paragraph summary. `--new` forces fresh. Pipelines and the
evaluator are **always** one-shot — no `session_id` passthrough, ever.

**Plugins** (Phase 2+, not yet implemented) will bundle multiple
skills — and optionally agents, pipelines, hooks — into a single
installable directory. The skill registry already supports multiple
search roots, so `plugins/<plugin-name>/skills/` will be picked up
automatically once the install command lands. See
`docs/ARCHITECTURE.md` "Agent Complexity Model" and `ROADMAP.md`
"Phase 5 — Plugin Marketplace".

## Build status

**Day 4 complete (4-A + 4-B + 4-C).** Bounded session continuity for
chatty modes, unified streamer, full v1 set of five pipelines,
interactive desktop GUI. **Day 5 next** — baseline session-start
checks, `crew logs`, `crew status`, `crew resume`, README polish,
end-to-end shakedown of all five pipelines on real team data.

For the per-day breakdown see `CHANGELOG.md`; for what's coming see
`ROADMAP.md`.
