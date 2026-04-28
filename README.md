# Crew

**Crew is to Copilot what Claude Code is to Claude** — a terminal-native
virtual assistant powered by the Copilot SDK, with optional governed
pipelines for team workflows that need structure.

Ask a question, get an answer. Ask for a workflow, get a structured run
with an isolated evaluator and a correction loop. The router decides;
override with a flag if you don't like the choice.

```bash
crew "what is 2+2?"                  # direct: one LLM call, MCP available
crew "fix the flaky test in foo.py"  # agent: persona swap (auto-summoned)
crew "standup prep"                  # pipeline: governed workflow
crew /debug "why is this failing?"   # skill: append capability, zero-cost dispatch
```

---

## Quickstart

Five commands from a fresh clone to a working answer:

```bash
git clone https://github.com/Eurus7895/CopilotCrew && cd CopilotCrew
pip install -e ".[dev]"          # CLI only ([dev,gui] for the desktop app)
copilot                          # one-time sign-in (or set GITHUB_TOKEN)
crew "what time is it?"          # direct mode, streams to terminal
crew /help                       # list pipelines, agents, skills
```

`github-copilot-sdk>=0.2.2` ships platform wheels that bundle the
`copilot` CLI binary, so you get the runtime with no extra steps.
Override with `COPILOT_CLI_PATH` to point at an existing install.

---

## Install

**Prerequisites.** Python 3.11+, a GitHub Copilot subscription *or* a
BYOK provider key (Anthropic, Azure, custom endpoint).

```bash
pip install -e ".[dev]"          # CLI only
pip install -e ".[dev,gui]"      # CLI + desktop GUI
```

**Authentication.** Two options:

1. **GitHub Copilot** — run `copilot` once and sign in; the SDK picks
   up the cached credential automatically on the next `crew` call.
2. **BYOK** — set `GITHUB_TOKEN`, or pass a `ProviderConfig` to the
   SDK. See the Copilot SDK docs.

---

## Usage

```bash
crew "<anything>"                    # router picks direct / agent / pipeline
crew /<skill> "<prompt>"             # skill invocation, zero LLM dispatch cost

crew --direct  "summarise this"      # force direct mode
crew --agent   coder "refactor X"    # force a specific agent
crew --pipeline "standup prep"       # force pipeline mode
crew --pipeline --summary "…"        # terse status lines (cron / CI)
crew --new "different topic"         # drop cached memory, start fresh

crew gui                             # desktop window (requires [gui] extra)
```

**Direct mode.** One Copilot SDK call with a generic assistant prompt,
MCP available, streamed to terminal. No output file.

**Agents** (`agents/<name>.md`). One LLM call with a persona's system
prompt — like direct mode, with a different voice. The router
auto-summons the best match based on the frontmatter `description`.
See `agents/coder.md` for the format.

**Skills** (`skills/<name>/SKILL.md`). Capability bundles
(Claude-Code-style): markdown instructions plus optional `scripts/` and
`references/`. Slash invocation appends the skill's instructions to
direct mode's system message — no router call. `/help` is built in and
prints the local registry without calling the SDK.

**Pipelines** (`pipelines/<name>/`). Governed workflows with plan JSON
and per-run output files. **Level 0** runs a single generator — hooks
fire, output goes to `~/.crew/outputs/<pipeline>/<timestamp>.md`.
**Level 1** adds an isolated evaluator session that grades the output
against a schema; failed verdicts retry up to 3 times before
`on-escalate` fires. Each attempt is preserved for audit. v1 ships
five: `daily-standup` and `release-notes` (L0); `incident-triage`,
`ticket-refinement`, `code-review-routing` (L1).

**Memory.** Direct, agent, and slash modes auto-resume per
`(cwd, mode, [agent|skill])` scope: the Copilot `session_id` is cached
in `~/.crew/sessions.json` and turns are appended to
`~/.crew/conversations/<scope>.jsonl`. At `CREW_TURN_CAP` turns
(default 20) the next call silently summarises the tail and starts a
fresh session seeded with the summary. `--new` forces fresh.
`CREW_SUMMARY_MODEL` selects a cheaper model for the summary call.
Pipelines and the evaluator **never** resume.

---

## GUI

`crew gui` opens an interactive desktop window with a three-pane
dashboard, three swappable design languages, live chat, and a visible
regenerate stream on the standup card. See [`docs/GUI.md`](docs/GUI.md)
for install, usage, packaging as a clickable app, and what's in the
window.

---

## Boundaries

**vs AgentShield.** AgentShield secures individual tool calls. Crew
governs what a pipeline produces across a full workflow.

**vs CopilotHarness.** IDE-native for coding. Crew is terminal-native
for team workflows. Same harness core, different surfaces.

**vs Claude Code.** Freeform agentic chat with plugins. Crew is
governed pipelines — every team-workflow request maps to a structured
pipeline with an isolated evaluator. Same plugin architecture
primitives, different execution model.

---

## Tests

```bash
python3 -m pytest -q
```

---

## Learn more

`CLAUDE.md` is the operational source of truth (rules, invariants,
state layout, env vars, the doc map). For deeper reading: design and
internals in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), schemas
and hook reference in [`docs/API.md`](docs/API.md), GUI in
[`docs/GUI.md`](docs/GUI.md), shipped work in
[`CHANGELOG.md`](CHANGELOG.md), what's next in
[`ROADMAP.md`](ROADMAP.md).
