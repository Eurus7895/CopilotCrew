# Architecture — Crew

How Crew works under the hood. For operational rules see `../CLAUDE.md`;
for hook + MCP schemas see `./API.md`.

---

## What Crew Is

Two fundamental modes (chatty vs governed), one interface. The router
decides which mode based on the request. The chatty side has two
flavours — generic assistant (`direct`) and persona swap
(`agent:{name}`); the router picks whichever matches best.

```
User types anything
        ↓
Intent Router (one LLM call)
  classifies: direct | agent:{name} | pipeline:{name}
        ↓
  ┌─────────────────────┬────────────────────────────────┐
  │  DIRECT MODE        │  PIPELINE MODE                 │
  │                     │                                │
  │  Simple request     │  Complex workflow              │
  │  Single LLM call    │  Governed pipeline             │
  │  No schema, no      │  Agents + evaluator +          │
  │  evaluator, no      │  validation + correction       │
  │  plan JSON          │  + plan JSON + audit           │
  │                     │                                │
  │  "what's our        │  "standup prep"                │
  │   sprint velocity?" │  "triage the API outage"       │
  │  "explain this      │  "refine PROJ-123"             │
  │   error message"    │  "release notes for v2.1"      │
  │  "how do I run      │  "who should review PR-421"    │
  │   the migrations?"  │                                │
  │                     │                                │
  │  Fast. Lightweight. │  Governed. Auditable.          │
  │  No overhead.       │  Reliable.                     │
  └─────────────────────┴────────────────────────────────┘
        ↓
Streaming terminal output
```

The router decides; the user can force either mode with `--direct` /
`--pipeline` / `--agent NAME`. Slash commands (`/standup`, `/debug`)
bypass the router — deterministic fast path.

---

## Origin & Lineage

```
CopilotHarness              Crew                     Claude Code
──────────────────────     ──────────────────────    ──────────────────
VS Code only               Terminal                  Terminal
Code tasks only             Any team workflow         Any coding task
Hardcoded 5-stage           Direct + pipelines        Freeform + plugins
VS Code LM API              Copilot SDK (BYOK)        Anthropic API
MCP server                  Plugin architecture       Plugin architecture
```

---

## Architecture — Adapted from Claude Code

Claude Code has five extension primitives. Crew adapts each one to
governed pipeline execution instead of freeform chat.

### 1. Agents — Markdown with YAML Frontmatter

Claude Code agents are markdown files with frontmatter that controls
model, tools, isolation, and behavior. Crew adopts the same format:

```markdown
---
name: incident-generator
description: Collects evidence and produces structured incident reports
model: gpt-4.1
maxTurns: 30
disallowedTools: Write, Edit
---

You are an incident response analyst. Given an incident description...
[full instructions below the frontmatter]
```

See `API.md` for the complete frontmatter field reference.

**Key insight from Claude Code:** The agent definition IS the prompt.
The frontmatter is configuration. The markdown body is the system prompt.
No separate config file needed. One file = one agent.

Generator agents live at: `pipelines/{name}/agents/generator.md`
Evaluator agents live at: `pipelines/{name}/agents/evaluator.md`

### 2. Skills — Auto-Invocation via LLM Reasoning

Claude Code skills don't use keyword matching or regex to decide when
to fire. The skill selection is pure LLM reasoning — all available
skills are formatted into a description, and the model decides which
to invoke based on context.

**Crew v1:** Manual injection per pipeline. Each `pipeline.yaml` lists
which skill to load. The skill loader reads `skills/SKILL.md` and
injects it into the generator's context.

**Crew v2+ (future):** Skills register trigger descriptions. The skill
loader presents all available skills to the intent router or generator.
The LLM decides which are relevant — no classifier, no regex.

See `API.md` for the skill frontmatter format.

**Key insight from Claude Code:** Skills are prompt template + context
injection + execution context modification. When a skill loads, it:
1. Injects instructions as new context into the agent
2. May modify allowed tools for that session
3. May reference scripts or data files in `skills/scripts/`

Skills live at: `skills/<name>/SKILL.md` (plus optional `references/`
and `scripts/`). Pipeline-bundled skills live at
`pipelines/{name}/skills/SKILL.md`. Global skills (future):
`~/.crew/skills/`.

### 3. Commands — Slash Commands as Markdown

Claude Code commands are markdown files in `.claude/commands/` that
become callable immediately. Crew adopts the same convention.

Commands live at: `.claude/commands/{name}.md`
Slash invocation: `/standup`, `/triage "API errors"`, `/refine PROJ-123`

**Key insight from Claude Code:** Commands bypass the intent router.
`/standup` goes directly to the standup pipeline — no LLM routing call,
no confidence check. Natural language goes through the router. Slash
commands are the deterministic fast path.

### 4. Hooks — Deterministic Code at Lifecycle Points

Claude Code hooks tie deterministic code to specific moments. They are
the mechanism for enforcing rules that LLMs cannot be trusted to follow
consistently.

**Key insight from Claude Code:** "Never send an LLM to do a linter's job."

See `API.md` for the full Crew hook reference and config format.

v1: hooks are Python scripts that log and enforce policy.
v2+: hooks support `type: "command"` (shell), `type: "http"` (webhook),
and `type: "agent"` (spawn an agent to handle the event).

### 5. MCP — External Tool Connections

Same as Claude Code's `.mcp.json`. Each pipeline can declare its own
MCP dependencies. Global MCP config lives at project root. See
`API.md` for the schema.

---

## Context Management — From Claude Code Internals

Claude Code's system prompt contains ~50 instructions. Adding CLAUDE.md,
skills, and plugin instructions on top crowds the context window.

**Implications for Crew:**

* **AGENTS.md must stay under 150 lines.** It goes into every session.
  Irrelevant instructions degrade performance. Keep it universally
  applicable.
* **Skills load on demand, not upfront.** The pipeline runner loads
  the relevant skill ONLY for the current pipeline. Global skills
  (v2+) are presented as descriptions — the LLM decides which to
  load, not the runner.
* **Evaluators get minimal context.** The evaluator receives the
  output text (inline) and the schema/criteria. Nothing else — no
  skill, no pipeline history, no generator instructions. Fresh eyes
  require fresh context.
* **Subagents for expensive reads.** If a generator needs to search
  1000 log lines, it should spawn a subagent for the search and
  receive only the summary. Primary context stays lean.
* **context_budget per pipeline (future):** When an agent's output
  exceeds a threshold, it must summarise before passing to the next
  stage.

---

## Pipeline Directory Layout

Each pipeline is a self-contained plugin following Claude Code conventions:

```
pipelines/
    standup/
        pipeline.yaml              ← level, mcp, correction config
        agents/
            generator.md           ← frontmatter + system prompt
        skills/
            SKILL.md               ← domain knowledge
        schemas/
            output.json            ← evaluator criteria (Level 1+)
        README.md                  ← documentation

    incident-triage/
        pipeline.yaml
        agents/
            generator.md           ← incident response analyst
            evaluator.md           ← skeptical QA (Level 1)
        skills/
            SKILL.md
        schemas/
            incident-report.json
        README.md
```

---

## Agent Complexity Model

```
Direct — Single LLM call, no pipeline
  No schema validation, no evaluator, no plan JSON, no hooks
  No skill injection, no baseline checks
  Just: prompt → response → print
  When: simple questions, explanations, quick lookups
  Speed: fastest possible — no overhead

Level 0 — Single agent pipeline, no evaluator
  Baseline checks, skill injection, plan JSON, hooks fire
  No evaluator — team feedback is the evaluator
  v1: daily-standup, release-notes

Level 1 — Single agent + separate evaluator (isolated session)
  Full governance: baseline, skills, schema, evaluator, correction loop
  v1: incident-triage, ticket-refinement, code-review-routing

Level 2 — Multi-agent + separate evaluator
  Promoted only after 3+ observed Level 1 failures
  Not in v1
```

**The router decides the mode.** Router classification:

```python
# intent_router.py

async def route(user_input: str) -> RouteResult:
    """
    One Copilot SDK call.
    Returns: { mode: "direct" | "agent" | "pipeline",
               name: str | None, params: dict }

    Prompt strategy:
      "You are a router. Given the user's request, decide:
       - simple question or quick task → mode=direct
       - matches a known persona description → mode=agent
       - matches a known pipeline → mode=pipeline
       Available pipelines: {PIPELINE_REGISTRY descriptions}
       Available agents:    {AGENT_REGISTRY descriptions}
       Return JSON only."
    """
```

**MCP is available in direct mode.** The direct session has access to
GitHub and Jira MCP — the user can ask "how many open PRs do we have?"
and get a direct answer without running the standup pipeline.

**Slash commands always bypass the router.** `/standup` goes directly
to the standup pipeline. `--direct` / `--agent` / `--pipeline` flags
let the user override the router.

---

## Execution Modes

### Direct Mode

```python
async def run_direct(
    user_input: str,
    *,
    session_id: str | None = None,   # Day 4-A: resume a prior session
    ...
) -> DirectResult:                   # (session_id, assistant_text)
    """Fastest path. No pipeline, no governance. Just answer."""
    async with CopilotClient() as client:
        async with await client.create_session(
            session_id=session_id,               # None → fresh session
            on_permission_request=PermissionHandler.approve_all,
            enable_config_discovery=True,        # MCP available
            streaming=True,
            ...
        ) as session:
            session.on(on_event)                 # streams to stdout
            await session.send_and_wait(user_input)
            return DirectResult(
                session_id=session.session_id,
                assistant_text=...,
            )
    # No plan JSON. Day 4-A added per-(cwd, mode, [agent]) session_id
    # caching in ~/.crew/sessions.json so the next invocation resumes.
```

### The Evaluator Pattern (Level 1)

```python
async def run_level_1(pipeline_config, params):
    # Generator session
    gen_client = CopilotClient()
    await gen_client.start()
    gen_session = await gen_client.create_session({
        "instructions": load_agent_md("generator.md"),  # frontmatter parsed
        "tools": parse_allowed_tools("generator.md"),
        "mcp_servers": pipeline_config.mcp_servers,
        "on_permission_request": policy_engine.check,
    })
    result = await gen_session.send_and_wait({"prompt": params.task})
    output_path = write_output(result)
    await gen_client.stop()

    # Evaluator — completely separate, minimal context
    for attempt in range(MAX_RETRIES):
        fire_hook("pre-eval", pipeline_config)
        eval_client = CopilotClient()
        await eval_client.start()
        eval_session = await eval_client.create_session({
            "instructions": load_agent_md("evaluator.md"),
            "tools": ["read"],                     # read only, never writes
        })
        verdict = await eval_session.send_and_wait({
            "prompt": f"Evaluate this output: {output_path}"
        })
        await eval_client.stop()

        if verdict_passes(verdict):
            fire_hook("post-run", pipeline_config, output_path)
            return output_path

        fire_hook("on-eval-fail", pipeline_config, verdict)

        # Retry with fresh generator + fix instructions
        gen_client = CopilotClient()
        await gen_client.start()
        gen_session = await gen_client.create_session({
            "instructions": load_agent_md("generator.md"),
            "tools": parse_allowed_tools("generator.md"),
            "mcp_servers": pipeline_config.mcp_servers,
            "on_permission_request": policy_engine.check,
        })
        result = await gen_session.send_and_wait({
            "prompt": f"{params.task}\n\nFix:\n{verdict.fix_instructions}"
        })
        output_path = write_output(result)
        await gen_client.stop()

    fire_hook("on-escalate", pipeline_config, output_path)
    return escalate(output_path)
```

`load_agent_md()` parses the frontmatter (YAML between `---`) for config
and the markdown body as the system prompt. Same pattern as Claude Code's
agent loader.

---

## Harness Core — Ported from CopilotHarness

```
copilot-harness/state.py         → crew/harness/state.py
copilot-harness/context_builder  → crew/harness/context_builder.py
copilot-harness/verifier.py      → crew/harness/verifier.py
copilot-harness/correction_loop  → crew/harness/correction_loop.py
copilot-harness/skill_loader.py  → crew/harness/skill_loader.py
copilot-harness/executor.py      → crew/harness/executor.py
```

All core logic unchanged. Paths and stage names updated. The Day 3
Level 1 loop is Copilot-SDK-native inside `pipeline_runner`; the
SQLite-stage modules (`correction_loop.py`, `state.py`, …) remain
dormant until a future workflow needs cross-stage state.

---

## GUI Rendering

`crew gui` opens a native PyWebView window. Internally a FastAPI +
Jinja2 + HTMX app runs on an ephemeral localhost port inside the app
process; the user-visible surface is a PyWebView window pointing at
it. No browser, no URL to remember, no visible server. A
`--no-window` flag drops back to a blocking server for CI / remote
dev.

### Three swappable design languages

Picked from `?theme=` query (sets a `crew_theme` cookie), the
`crew_theme` cookie, or default (`warm`). Picker lives at `/settings`.

- **Warm · Workspace** (default) — warm neutrals, paper cards,
  polaroid avatar, "A gentle note" panel, chat-style "Tell Crew
  about…" input.
- **Terminal · Operator** — tmux-style console, phosphor amber on
  black, ASCII section rules, vim keybinding hints, `crew>` prompt.
- **Modernist · Swiss** — Archivo 900 + signal-red, giant `01/05`
  numerals, `§01` section markers, "BY THE NUMBERS" right rail.

### File layout

```
crew/gui/
    __main__.py                bundle entrypoint (PyInstaller-friendly)
    server.py                  uvicorn launcher + window controller
    routes/
        _shared.py             theme resolver (?theme= → cookie → default)
        chat.py                POST /chat → crew.direct.run_direct
        pinned.py              POST /pinned/{kind}/{name} dispatch
        standup.py             /standup/run + #standup-progress SSE
        events.py              SSE bus
    services/
        chat_service           bridges chat to crew.direct (lazy SDK import)
        pinned, pinned_actions registry-driven left-rail
        standup_service        regenerate lock + pipeline_progress events
        status_service         model label, registries summary
        editor                 $EDITOR launcher for memory.jsonl
        events_bus             pub/sub for SSE
        bootstrap              seeds ~/.crew/gui/*.jsonl on first run
        mocks                  stub timeline / PR / Slack data sources
    templates/themes/{warm,terminal,modernist}/
        chat_turn.html         user + assistant bubble fragments
        ...
    static/themes/<name>.css
```

### Three panes

- **Left rail** — pinned slash commands / agents / pipelines drawn
  from the real registries, plus a day timeline.
- **Center** — greeting, cards for overnight PR activity and Slack
  mentions, the latest daily-standup draft (live from
  `~/.crew/outputs/daily-standup/`), and an action row. *Post to
  #standup* is disabled until Slack integration lands; *Regenerate*
  re-runs the `daily-standup` pipeline with stdout captured into an
  SSE bus; *Edit draft* opens the output in `$EDITOR`; *Skip today*
  deletes the latest draft.
- **Right rail** — context panel. Per-theme content: Warm shows
  recent observations + a gentle note, Terminal shows `~/CONTEXT` kv
  table + `~/MEMORY.JSONL`, Modernist shows "BY THE NUMBERS" stats +
  editorial observations.

### Streaming bridge

Chat reuses `crew.direct.run_direct` via a `CallbackStreamer` that
publishes per-token events onto the SSE bus. Pipeline invocation
reuses `pipeline_runner.run_pipeline` (a module lock blocks
concurrent runs). Copilot SDK imports inside `chat_service` and
`standup_service` are lazy so the GUI boots even without the SDK
for read-only use.

---

## Resources

- Copilot SDK Python: https://github.com/github/copilot-sdk/tree/main/python
- Copilot SDK BYOK: https://docs.github.com/en/copilot/how-tos/copilot-sdk/authenticate-copilot-sdk/bring-your-own-key
- Claude Code plugins reference: https://code.claude.com/docs/en/plugins-reference
- Claude Code plugin registry: https://github.com/anthropics/claude-plugins-official
- Claude Code skills deep dive: https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/
- Harness best practices: https://github.com/celesteanders/harness/blob/main/docs/best-practices.md
- CopilotHarness: https://github.com/Eurus7895/CopilotHarness
