# CLAUDE.md — Crew

Operational rules, invariants, and commands. Read this when making
architecture decisions; read `AGENTS.md` for session-start orientation.

**Crew is to Copilot what Claude Code is to Claude — with optional
governed pipelines for team workflows that need structure.**

| Doc | Purpose |
|---|---|
| `README.md` | Pitch, install, usage, boundaries |
| `AGENTS.md` | Session-start map (project shape) |
| `CHANGELOG.md` | Completed work, week by week |
| `ROADMAP.md` | Day 5, known TODOs, evolution path, risks |
| `docs/ARCHITECTURE.md` | How it works, file layout, GUI rendering |
| `docs/API.md` | Frontmatter, hooks, MCP, policy schemas |

---

## Core Design Principles

**1. Single agent first.** Multi-agent only when one demonstrably
fails.

**2. Separate evaluator session.** Fresh context. No shared state.
Non-negotiable.

**3. Structured artifacts survive context resets.** JSON to disk.
Always.

**4. Verify baseline before running.** MCP alive? Last output intact?

**5. Skill files fix bad output first.** Before changing pipeline
level.

**6. Pipelines are self-contained directories.** Shareable,
installable, removable as a unit.

**7. Hook injection points from Day 1.** Even if hooks just log in v1.

**8. Context is scarce.** Offload expensive work to subagents. Keep
primary context lean.

**9. Re-evaluate harness per model upgrade.** Strip what models no
longer need.

---

## Operational Invariants

These are enforced by tests and must not be relaxed without a
principle change:

* **Pipelines + the evaluator NEVER resume.** No `session_id` is ever
  passed to `create_session` from `crew/pipeline_runner.py` or
  `crew/evaluator.py`. Two runtime guard tests assert this. Principle
  #2 is non-negotiable.
* **Evaluator gets minimal context.** Output text + schema. No MCP,
  no skill, no tools, no pipeline history, no generator instructions.
  `enable_config_discovery=False`. System message is
  `evaluator_prompt + schema_text` in `replace` mode.
* **Each attempt is preserved.** Failed attempts land in
  `~/.crew/outputs/<pipeline>/<ts>-<uid>-attempt{N}.md` with the
  per-run plan JSON capturing the full `attempts` array and an
  `escalated` flag.
* **Hooks are deterministic.** "Never send an LLM to do a linter's
  job." Anything that must happen the same way every time belongs in
  a hook, not in the agent's instructions.
* **Slash commands bypass the router.** `/<skill>` and `/<pipeline>`
  go directly to the right handler — no LLM routing call.
* **Skill / agent / pipeline registries are file-driven.** Drop the
  directory in, the registry picks it up. No registration code.
* **AGENTS.md must stay under 150 lines.** It goes into every
  session.

---

## Common Commands

```bash
crew "what is 2+2?"                  # router → direct mode
crew "fix the flaky test in foo.py"  # router → agent:coder (auto-summon)
crew "standup prep"                  # router → daily-standup (Level 0)
crew "triage the API outage"         # router → incident-triage (Level 1)
crew /debug "why is this failing?"   # skill: appends debug methodology
crew /help                           # list pipelines, agents, skills

crew --direct "summarise this"       # force direct mode
crew --agent coder "refactor X"      # force a specific agent
crew --pipeline "standup prep"       # force pipeline mode
crew --pipeline --summary "…"        # terse status lines (cron / CI)
crew --new "different topic"         # drop cached memory, start fresh

crew gui                             # native PyWebView desktop window
crew gui --no-window --open          # headless + system browser

python3 -m pytest -q                 # tests
```

---

## State

```
~/.crew/
    outputs/                     generated files
    plans/                       JSON state per run (survives context resets)
    eval_feedback/               evaluator verdicts
    logs.db                      SQLite audit log (WAL mode)
    progress.md                  session notes — append per run, read at start
    config.yaml                  auth, model, output preferences
    sessions.json                per-scope Copilot session_id cache
    conversations/<scope>.jsonl  per-scope turn log (rotation input)
    memory.jsonl                 remembered facts (GUI right rail)
    gui/                         JSONL stubs the dashboard reads
```

**Scope** = `(mode, agent_or_skill, cwd)` hashed for filesystem
safety. The readable cwd is stored inside the session value for
audit only. Slash commands carry per-skill memory: `/debug` in projA
and `/debug` in projB are separate threads.

---

## Environment Variables

* `CREW_HOME` — root directory (default `~/.crew`)
* `CREW_TURN_CAP` — turns per chatty session before summary rotation
  (default 20)
* `CREW_SUMMARY_MODEL` — model for the rotation summary call
  (default: same as the user's model; set to a smaller / cheaper
  model to keep context-management work off the primary model)
* `COPILOT_CLI_PATH` — override the bundled `copilot` binary
* `GITHUB_TOKEN` — BYOK fallback when no Copilot subscription is
  available

---

## Build Status

**Day 4 complete (4-A + 4-B + 4-C).** Bounded session continuity for
chatty modes, unified streamer, full v1 set of five pipelines, and
an interactive desktop GUI.

**Day 5 is next** — baseline session-start checks, `crew logs`,
`crew status`, `crew resume`, README polish, end-to-end shakedown
of all five pipelines on real team data, and handing the tool to
the first team member. See `ROADMAP.md` for the full punch list.

---

*Updated: April 2026*
*Product: Crew · Phase: Day 4 complete; Day 5 hardening next*
