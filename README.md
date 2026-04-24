# Crew

Terminal-native virtual assistant powered by the Copilot SDK. See `CLAUDE.md`
for the full design doc and `AGENTS.md` for session-start orientation.

## Status

**Day 4-A of the build order, plus the desktop GUI.** Level 1 pipelines
ship with an isolated evaluator + correction loop
(`pipelines/incident-triage/`); direct + agent + slash modes auto-resume
their per-(cwd, mode, [agent|skill]) Copilot session and rotate silently
every ~20 turns (`--new` starts fresh). `crew gui` opens a native
desktop window (PyWebView) showing a three-pane "always-open pane" with
pinned commands, a day timeline, the latest standup draft, and a
remembered-facts panel — rendered in any of three design languages
(Warm · Workspace, Terminal · Operator, Modernist · Swiss) swappable
from a tab strip. Sits on top of Day 3 (evaluator + `incident-triage`),
Day 2.8 (slash commands invoke skills; `skills/debug/`), Day 2.5's
3-way intent router (direct / agent / pipeline), and Day 2's pipeline
runner + hook registry. Pipelines and the evaluator are always one-shot
(CLAUDE.md principle #2). Plugin bundles (shareable directories of
skills) are roadmapped for Phase 2+.

## Install

```bash
pip install -e ".[dev]"          # CLI only
pip install -e ".[dev,gui]"      # CLI + desktop GUI
```

The `[gui]` extra pulls in FastAPI, uvicorn, Jinja2, sse-starlette, and
PyWebView. PyWebView uses the OS's native webview — usually already
installed. On Linux you may need `sudo apt install libwebkit2gtk-4.1-0`
(or `libwebkit2gtk-4.0-37` on older distros).

`github-copilot-sdk>=0.2.2` ships platform wheels that bundle the `copilot`
CLI binary, so pip picks the right wheel for your OS/arch and you get the
runtime with no extra steps. Override with `COPILOT_CLI_PATH` to point at an
existing install.

## Authentication

Direct mode needs either a GitHub Copilot subscription or a BYOK provider
key. Two options:

1. **GitHub Copilot** — run `copilot` once and sign in; the SDK picks up the
   cached credential automatically on the next `crew` invocation.
2. **BYOK** — set `GITHUB_TOKEN`, or pass a `ProviderConfig` (Anthropic,
   Azure, custom endpoint) to the SDK. See the Copilot SDK docs.

## Usage

```bash
crew "what is 2+2?"                  # router → direct mode
crew "fix the flaky test in foo.py"  # router → agent:coder (auto-summoned)
crew "standup prep"                  # router → daily-standup (Level 0)
crew "triage the API outage"         # router → incident-triage (Level 1)
crew /debug "why is this failing?"   # skill: appends debug methodology
crew /help                           # list pipelines, agents, skills
crew --direct "summarise this"       # force direct mode (skips the router)
crew --agent coder "refactor X"      # force a specific standalone agent
crew --pipeline "standup prep"       # force pipeline mode (router picks which)
crew --new "different topic"         # drop cached memory, start fresh
crew gui                             # launch the desktop GUI (native window)
crew gui --no-window --open          # headless mode + system browser
```

**Slash commands** (`/<skill>`) invoke a skill from `skills/<name>/SKILL.md`.
The skill's instructions are appended to the session's system message and
the call runs as direct mode underneath — zero LLM cost for the dispatch.
`/help` is a built-in that prints the local registry (pipelines, agents,
skills) without calling the SDK. Unknown names exit with code 2 and list
the available commands.

**Agents** (`agents/*.md`) are persona swaps: one LLM call like direct
mode, but with the agent's system prompt. No output file, no plan JSON.
The intent router auto-summons the best-matching agent based on the
frontmatter `description`. See `agents/coder.md` for the format.

**Skills** (`skills/<name>/SKILL.md`) are task-specific capability bundles
(Claude-Code style): markdown instructions + optional `scripts/` and
`references/` directories. See `skills/debug/SKILL.md` for the format.

**Plugins** (roadmapped, Phase 2+) will bundle multiple skills into a
single installable directory under `plugins/<plugin-name>/skills/`; a
future `crew install <name>@<repo>` command will drop them in. The skill
registry already supports multiple search roots so no format migration
is required when plugins land.

**Pipelines** are governed workflows with plan JSON and per-run output
files. **Level 0** (`pipelines/standup/`) runs a single generator — hooks
fire, output goes to `~/.crew/outputs/<pipeline>/<timestamp>.md`, plan
manifest to `~/.crew/plans/<session-id>.json`. **Level 1**
(`pipelines/incident-triage/`) adds an isolated evaluator session (fresh
`CopilotClient`, no MCP, no tools) that grades the generator's output
against a schema; on a failed verdict the generator is re-spawned with
the verdict's fix instructions, up to 3 attempts before `on-escalate`
fires. Each attempt's output is preserved for audit.

**Memory.** Direct + agent + slash modes auto-resume per
`(cwd, mode, [agent|skill])` scope: the Copilot `session_id` is cached
in `~/.crew/sessions.json` and turns are appended to
`~/.crew/conversations/<scope>.jsonl` as rotation input. At
`CREW_TURN_CAP` turns (default 20) the next call silently summarises
the tail and starts a fresh SDK session seeded with the summary.
`--new` forces fresh; `CREW_SUMMARY_MODEL` selects a cheaper model
for the summary call. Pipelines and the evaluator **never** resume.

## GUI

`crew gui` opens a native desktop window. Internally a FastAPI +
Jinja2 + HTMX app runs on an ephemeral localhost port inside the app
process; the user-visible surface is a PyWebView window pointing at it.
No browser, no URL to remember, no visible server.

```bash
pip install -e ".[gui]"
crew gui                        # desktop window, ephemeral port
crew gui --model gpt-4o         # status-bar model label override
crew gui --no-window --open     # headless / CI / screencast: run the
                                # server on 127.0.0.1:8765 and open
                                # the system browser
```

### Ship as a clickable app

Teammates shouldn't need a Python toolchain to run Crew. Package the
GUI as a double-clickable bundle with PyInstaller:

```bash
pip install -e '.[gui,package]'
python packaging/build.py
```

Outputs land in `dist/`:

- `dist/Crew.app` — macOS bundle
- `dist/Crew/Crew.exe` — Windows
- `dist/Crew/Crew` — Linux

See `packaging/README.md` for icons, code-signing, and a cross-platform
GitHub Actions matrix.

Three panes, three swappable design languages (tab strip at the top):

- **Warm · Workspace** (default) — warm neutrals, paper cards, polaroid
  avatar, "A gentle note" panel, chat-style "Tell Crew about…" input.
- **Terminal · Operator** — tmux-style console, phosphor amber on black,
  ASCII section rules, vim keybinding hints, `crew>` prompt.
- **Modernist · Swiss** — Archivo 900 + signal-red, giant `01/05`
  numerals, `§01` section markers, "BY THE NUMBERS" right rail.

Content inside each pane:

- **Left rail** — pinned slash commands / agents / pipelines drawn from
  the real registries, plus a day timeline.
- **Center** — greeting, cards for overnight PR activity and Slack
  mentions, the latest daily-standup draft (live from
  `~/.crew/outputs/daily-standup/`), and an action row. *Post to
  #standup* is disabled until Slack integration lands; *Regenerate*
  re-runs the `daily-standup` pipeline with stdout captured into an SSE
  bus; *Edit draft* opens the output in `$EDITOR`; *Skip today*
  deletes the latest draft.
- **Right rail** — context panel. Per-theme content: Warm shows recent
  observations + a gentle note, Terminal shows `~/CONTEXT` kv table +
  `~/MEMORY.JSONL`, Modernist shows "BY THE NUMBERS" stats + editorial
  observations.

Aspirational data (timeline events, remembered facts, PR/Slack cards,
working-on chips) read from JSONL files seeded into `~/.crew/gui/` and
`~/.crew/memory.jsonl` on first launch. Edit them by hand or let future
hooks/pipelines append — the window picks up changes on the next
request. Internal server binds `127.0.0.1` only; no auth in v1.

## Tests

```bash
python3 -m pytest -q
```
