# CLAUDE.md — Crew
### Full Design Document

> This is the design doc. Read it when making architecture decisions.
> For session-start orientation, read AGENTS.md instead.

---

## One Sentence

Crew is a terminal-native virtual assistant powered by Copilot SDK. Simple
requests get a direct response. Complex workflows route to governed pipelines
with validation, correction loops, and audit trails.

**Crew is to Copilot what Claude Code is to Claude — with optional governed
pipelines for team workflows that need structure.**

---

## What Crew Is

Two modes, one interface. The router decides which mode based on the request.

```
User types anything
        ↓
Intent Router (one LLM call)
  classifies: direct | pipeline
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

**The router decides, not the user.** But the user can force either mode:

```bash
crew "what's our sprint velocity?"        # router decides → likely direct
crew "standup prep"                        # router decides → likely pipeline
crew --direct "summarize this file"        # force direct mode
crew --pipeline "summarize this file"      # force pipeline mode
/standup                                   # slash command → always pipeline
```

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

## Core Design Principles

**1. Single agent first.** Multi-agent only when one demonstrably fails.

**2. Separate evaluator session.** Fresh context. No shared state. Non-negotiable.

**3. Structured artifacts survive context resets.** JSON to disk. Always.

**4. Verify baseline before running.** MCP alive? Last output intact?

**5. Skill files fix bad output first.** Before changing pipeline level.

**6. Pipelines are self-contained directories.** Shareable, installable, removable as a unit.

**7. Hook injection points from Day 1.** Even if hooks just log in v1.

**8. Context is scarce.** Offload expensive work to subagents. Keep primary context lean.

**9. Re-evaluate harness per model upgrade.** Strip what models no longer need.

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

**Frontmatter fields used by Crew:**

| Field | Purpose | Crew usage |
|---|---|---|
| `name` | Agent identifier | Pipeline routing |
| `description` | When to invoke this agent | Intent router matching |
| `model` | Which model to use | Copilot SDK model selection |
| `maxTurns` | Max tool call iterations | Prevents infinite loops |
| `disallowedTools` | Tools this agent cannot use | Principle of least privilege |
| `skills` | Auto-load these skills | Skill injection per agent |
| `isolation` | Run in isolated context | Evaluator always isolated |

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

**Skill format (same as Claude Code):**

```markdown
---
name: incident-response
description: Domain knowledge for incident triage and root cause analysis.
  Auto-invoke when the task involves investigating outages, errors, or
  service failures.
allowed-tools: Read, Bash
version: 1.0.0
---

## Purpose
[what this skill teaches the agent]

## Key Domain Knowledge
[facts the agent needs that aren't obvious]

## Common Mistakes to Avoid
[specific failure patterns — this section grows from real failures]

## Output Quality Bar
[what a passing evaluator verdict looks like]
```

**Key insight from Claude Code:** Skills are prompt template + context
injection + execution context modification. When a skill loads, it:
1. Injects instructions as new context into the agent
2. May modify allowed tools for that session
3. May reference scripts or data files in `skills/scripts/`

Skills live at: `pipelines/{name}/skills/SKILL.md`
Global skills (future): `~/.crew/skills/` — apply across all pipelines.

### 3. Commands — Slash Commands as Markdown

Claude Code commands are markdown files in `.claude/commands/` that
become callable immediately. Crew adopts the same convention:

```markdown
---
description: Run daily standup pipeline
argument-hint: [date]
---

Run the daily-standup pipeline.

If $ARGUMENTS contains a date, use that date.
Otherwise, use yesterday's date.

Load the pipeline from pipelines/standup/.
Follow the session protocol in AGENTS.md.
```

Commands live at: `.claude/commands/{name}.md`
Slash invocation: `/standup`, `/triage "API errors"`, `/refine PROJ-123`

**Key insight from Claude Code:** Commands bypass the intent router.
`/standup` goes directly to the standup pipeline — no LLM routing call,
no confidence check. Natural language goes through the router. Slash
commands are the deterministic fast path.

### 4. Hooks — Deterministic Code at Lifecycle Points

Claude Code hooks tie deterministic code to specific moments:
`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`, `PermissionRequest`.
They are the mechanism for enforcing rules that LLMs cannot be trusted
to follow consistently.

**Key insight from Claude Code:** "Never send an LLM to do a linter's job."
Anything that must happen the same way every time belongs in a hook, not
in the agent's instructions.

**Crew hooks and their types:**

| Hook | Claude Code equivalent | Type | When |
|---|---|---|---|
| `session-start` | `SessionStart` | `command` | Before pipeline run |
| `pre-tool-use` | `PreToolUse` | `command` | Before every tool call |
| `post-tool-use` | `PostToolUse` | `command` | After every tool call |
| `on-eval-fail` | (custom) | `command` | Evaluator rejects output |
| `on-escalate` | (custom) | `command` | Max retries exceeded |

**Hook config format (adapted from Claude Code `hooks.json`):**

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 crew/hooks/pre_tool_use.py"
      }]
    }],
    "SessionStart": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 crew/hooks/session_start.py"
      }]
    }]
  }
}
```

v1: hooks are Python scripts that log and enforce policy.
v2+: hooks support `type: "command"` (shell), `type: "http"` (webhook),
and `type: "agent"` (spawn an agent to handle the event).

### 5. MCP — External Tool Connections

Same as Claude Code's `.mcp.json`. Each pipeline can declare its own
MCP dependencies. Global MCP config lives at project root.

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/"
    },
    "jira": {
      "type": "http",
      "url": "https://your-instance.atlassian.net/mcp",
      "headers": { "Authorization": "Bearer ..." }
    }
  }
}
```

---

## Context Management — From Claude Code Internals

Claude Code's system prompt contains ~50 instructions. Adding CLAUDE.md,
skills, and plugin instructions on top crowds the context window.

**Implications for Crew:**

**AGENTS.md must stay under 150 lines.** It goes into every session.
Irrelevant instructions degrade performance. Keep it universally applicable.

**Skills load on demand, not upfront.** The pipeline runner loads the
relevant skill ONLY for the current pipeline. Global skills (v2+) are
presented as descriptions — the LLM decides which to load, not the runner.

**Evaluators get minimal context.** The evaluator receives:
- The output file path
- The schema/criteria
- Nothing else — no skill, no pipeline history, no generator instructions
This is deliberate. Fresh eyes require fresh context.

**Subagents for expensive reads.** If a generator needs to search 1000
log lines, it should spawn a subagent for the search and receive only
the summary. Primary context stays lean. Same pattern as Claude Code's
Task/Explore tools and Ralph Wiggum's subagent strategy.

**context_budget per pipeline (future):** When an agent's output exceeds
a threshold, it must summarise before passing to the next stage. This
keeps pipeline context lean across multi-agent Level 2 runs.

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

**The router decides the mode.** It classifies every request as one of:
- `direct` — answer immediately, no pipeline
- `pipeline:{name}` — route to a specific pipeline

Router classification logic:
```python
# intent_router.py

async def route(user_input: str) -> RouteResult:
    """
    One Copilot SDK call.
    Returns: { mode: "direct" | "pipeline", pipeline: str | None, params: dict }

    Prompt strategy:
      "You are a router. Given the user's request, decide:
       - If this is a simple question, explanation, or quick task: return mode=direct
       - If this matches a known pipeline: return mode=pipeline with the pipeline name
       Available pipelines: {PIPELINE_REGISTRY descriptions}
       Return JSON only."
    """
```

**MCP is available in direct mode.** The direct session has access to
GitHub and Jira MCP — the user can ask "how many open PRs do we have?"
and get a direct answer without running the standup pipeline.

**Slash commands always route to pipeline.** `/standup` never goes to direct mode.
`--direct` and `--pipeline` flags let the user override the router.

---

## Execution Modes

### Direct Mode

```python
async def run_direct(user_input: str):
    """Fastest path. No pipeline, no governance. Just answer."""
    client = CopilotClient()
    await client.start()
    session = await client.create_session({
        "instructions": "You are a helpful team assistant.",
        "mcp_servers": load_global_mcp(),    # MCP available for data lookups
        "on_permission_request": PermissionHandler.approve_all,
    })

    # Stream the response directly to terminal
    session.on(lambda event: streamer.handle(event))
    await session.send_and_wait({"prompt": user_input})
    await client.stop()
    # No plan JSON, no SQLite log, no progress.md — just answer and done
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

## State

```
~/.crew/
    outputs/                     generated files
    plans/                       JSON state per run (survives context resets)
    eval_feedback/               evaluator verdicts
    logs.db                      SQLite audit log (WAL mode)
    progress.md                  session notes — append per run, read at start
    config.yaml                  auth, model, output preferences
    sessions.json                per-scope Copilot session_id cache (Day 4-A)
    conversations/<scope>.jsonl  per-scope turn log (audit trail; Day 4-A)
```

Env vars affecting state:
* `CREW_HOME` — root directory (default `~/.crew`)
* `CREW_TURN_CAP` — turns per chatty session before summary rotation
  (default 20)
* `CREW_SUMMARY_MODEL` — model for the rotation summary call (default:
  same as the user's model; set to a smaller / cheaper model to keep
  context-management work off the primary model)

---

## Policy Engine

```python
PIPELINE_POLICIES = {
    "daily-standup":       ["read", "mcp"],
    "release-notes":       ["read", "mcp"],
    "incident-triage":     {
        "generator": ["read", "shell", "mcp"],
        "evaluator": ["read"],
    },
    "ticket-refinement":   {
        "generator": ["read", "write", "mcp"],
        "evaluator": ["read"],
    },
    "code-review-routing": {
        "generator": ["read", "mcp"],
        "evaluator": ["read"],
    },
}
```

Enforced via `pre-tool-use` hook — deterministic, not prompt-based.
"Never send an LLM to do a linter's job."

---

## Build Order

### Day 1 — SDK smoke test + direct mode
```
[ ] Copilot SDK quickstart: one agent, one prompt, prints response
[ ] Copy harness core from CopilotHarness (6 files), update paths
[ ] Implement direct mode: crew "hello" → streamed response
[ ] Implement load_agent_md(): parse frontmatter + markdown body
[ ] Direct mode works with MCP (crew "how many open PRs?")
    → Direct mode is the foundation. Everything else builds on it.
```

### Day 2 — Intent router + standup (Level 0)
```
[x] intent_router.py: classify direct vs pipeline:{name}
[x] PIPELINE_REGISTRY with descriptions for router matching
[x] Load pipeline from pipelines/standup/ directory
[x] pipeline_runner.py Level 0 execution
[x] Hook injection points: session-start, pre-tool-use, post-tool-use
[x] Test: crew "standup prep" → routes to pipeline → output file
[x] Test: crew "what time is it?" → routes to direct → inline answer
[x] --direct and --pipeline override flags work
```

### Day 2.5 / 2.75 / 2.8 — Agents, slash commands, skills
Incremental slices landed alongside Day 2 to close the ergonomics gap
before Day 3's evaluator work:
```
[x] agents/<name>.md — standalone persona swaps (--agent NAME + auto-summon)
[x] Intent router upgraded to 3-way (direct / agent / pipeline)
[x] Slash commands invoke skills at skills/<name>/SKILL.md
[x] skill_registry supports multiple search roots (plugin-ready)
[x] skills/debug/ — first shipped skill
```

### Day 3 — Evaluator + incident-triage (Level 1)
```
[x] evaluator.py: separate CopilotClient factory + verdict parser
[x] pipeline_runner.py Level 1 execution with isolated evaluator
[x] Hook injection: on-eval-fail, on-escalate
[x] Test: evaluator grades in fresh session, correction loop fires
```

Implementation notes:

* The evaluator receives the generator's output **text** inline, not a
  file path. Its session has no MCP and no permission handler, so it
  cannot read files anyway — passing the path would buy nothing. This
  stays faithful to "fresh eyes, fresh context".
* Evaluator session uses `enable_config_discovery=False`. No MCP, no
  skill, no tools. System message is `evaluator_prompt` plus the
  pipeline's `schema_text`, in `replace` mode.
* Each attempt's output is preserved on disk
  (`~/.crew/outputs/<pipeline>/<ts>-<uid>-attempt{N}.md`) so a failed
  run is auditable. The single per-run plan JSON contains the full
  `attempts` array (per-attempt verdict, output path, timestamps) and
  an `escalated` flag.
* `run_pipeline(config, ...)` dispatches by `config.level` (0 → Level
  0; 1 → Level 1; 2+ → ValueError). The CLI now calls `run_pipeline`
  exclusively; `run_level_0` / `run_level_1` stay exported for tests.
* `crew/harness/correction_loop.py` (the SQLite-stage harness ported
  from CopilotHarness) stays dormant — its plan→design→code→review
  contract doesn't fit the generator/evaluator loop. The Day 3 loop
  lives inside `pipeline_runner.run_level_1` instead.

### Day 4-A — Bounded session continuity for chatty modes
```
[x] crew/conversations.py: per-scope session_id cache + rotation log
[x] crew/direct.py: accept session_id, return DirectResult (id + text)
[x] crew/cli.py: --new flag + memory wrapper (zero additional CLI surface)
[x] Summary rotation when CREW_TURN_CAP turns reached (CREW_SUMMARY_MODEL
    selects the summariser model; default: user's current model)
[x] Pipelines + evaluator stay one-shot (runtime guard tests)
```

Implementation notes:

* **Minimal surface by design.** Users don't manage sessions — they just
  chat. The only user-facing knob is `--new` (forget and start over).
  An earlier draft added `--session NAME`, `--no-memory`, and a
  `crew sessions {list,show,clear}` subcommand; all three were dropped
  as surplus surface once the real requirement became clear.
* **Scope = (mode, agent_or_skill, cwd)** hashed for filesystem safety.
  The readable cwd is stored inside the session value for audit but is
  not user-facing.
* **Slash commands carry per-skill memory.** `scope = ("slash",
  skill_name, cwd)` so `/debug` in projA and `/debug` in projB are
  separate threads, and neither pollutes bare direct mode.
* **JSONL is rotation input, not a user surface.** Each turn appends
  one row to `~/.crew/conversations/<scope>.jsonl`; rotation reads the
  tail to produce the handoff summary, then writes a `rotated` event
  marker. The log is internal plumbing — no CLI exposes it.
* **Pipelines + evaluator NEVER resume.** Principle #2 is non-negotiable.
  Two runtime guard tests assert `session_id` never appears in
  `create_session` kwargs from `pipeline_runner` or the evaluator.

### Day 4-B — Streaming + remaining pipelines
```
[ ] streamer.py: terminal output + summary mode
[ ] ticket-refinement, code-review-routing, release-notes
[ ] Test all 5 pipelines end-to-end on real team data
```

### Day 5 — Hardening + first team member
```
[ ] Baseline checks in session-start hook
[ ] crew logs, crew status, crew resume
[ ] README: install in 5 minutes
[ ] Give to 1 team member. Watch. Take notes.
```

---

## Evolution Path

Designed now. Not building in v1.

### Phase 2 — Plugin + Pipeline Install (Month 2+)
`crew install` = copy a directory into the project. A plugin bundles
multiple skills (and optionally agents, pipelines, hooks) under
`plugins/<name>/` with a `plugin.yaml` manifest and nested `skills/`,
`agents/`, `pipelines/` directories. The v1 file formats ARE the install
formats — no migration. The skill registry already supports multiple
search roots (local `skills/` + any `plugins/*/skills/`), so activating
plugin discovery is a registry-wiring change, not a format redesign.

### Phase 3 — Auto-Invoke Skills (Month 3+)
Skills register trigger descriptions in frontmatter. LLM decides which
to load — no classifier, no regex. Same mechanism as Claude Code skills.
Day 2.8 shipped explicit skill invocation via `/skill-name`; Phase 3 adds
the auto-invoke path without changing the skill file format.

### Phase 4 — Custom Hooks (Month 3+)
Hooks become executable: `type: command` (shell), `type: http` (webhook),
`type: agent` (spawn agent to handle event). Follows Claude Code hook types.

### Phase 5 — Plugin Marketplace (Month 6+)
GitHub repo of validated plugins. `crew install name@crew-plugins-official`
fetches and installs. Plugin-as-directory format = marketplace entry
format (see Phase 2). No migration.

### Phase 6 — SSO / Enterprise Auth (Month 4+)
Only after team adoption proven.

### Phase 7 — Web Dashboard (Month 6+)
Read-only view of logs.db + plans/. FastAPI + HTMX. CLI remains primary.

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

All core logic unchanged. Paths and stage names updated.

---

## Boundaries

**vs AgentShield:** AgentShield secures individual tool calls.
Crew governs what a pipeline produces across a full workflow.

**vs CopilotHarness:** IDE-native for coding. Crew is terminal-native
for team workflows. Same harness core. Different surfaces.

**vs Claude Code:** Freeform agentic chat with plugins. Crew is governed
pipelines — every request maps to a structured workflow. Same plugin
architecture primitives, different execution model.

---

## Risks

| Risk | Probability | Mitigation |
|---|---|---|
| SDK Public Preview breaks | Medium | BYOK Anthropic adapter |
| MCP unreliable | Medium | Graceful degradation |
| Intent router misroutes | High initially | Slash commands bypass router |
| Evaluator too strict/loose | Medium | Start lenient, tune after baseline |
| Team doesn't adopt | Medium | Ship Day 5, watch, don't assume |
| Premature Level 2 | High risk | Promotion checklist mandatory |
| Claude Code ships team workflows | Low-Medium | Cross-LLM via BYOK |

---

## Not Building in v1

```
❌ Level 2 pipelines         ❌ Pipeline marketplace
❌ Auto-invoke skills        ❌ Executable hooks (beyond Python scripts)
❌ Web dashboard             ❌ SSO / enterprise auth
❌ Cloud deployment          ❌ Multi-user sessions
❌ More than 5 pipelines     ❌ context_budget enforcement
```

---

## Resources

- Copilot SDK Python: https://github.com/github/copilot-sdk/tree/main/python
- Copilot SDK BYOK: https://docs.github.com/en/copilot/how-tos/copilot-sdk/authenticate-copilot-sdk/bring-your-own-key
- Claude Code plugins reference: https://code.claude.com/docs/en/plugins-reference
- Claude Code plugin registry: https://github.com/anthropics/claude-plugins-official
- Claude Code skills deep dive: https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/
- Harness best practices: https://github.com/celesteanders/harness/blob/main/docs/best-practices.md
- CopilotHarness: https://github.com/Eurus7895/CopilotHarness

---

*Updated: April 2026*
*Product: Crew*
*Phase: Day 4-A shipped; Day 4-B next*
*First user: Current team*
*Next: Day 4-B — streamer + remaining pipelines (ticket-refinement, code-review-routing, release-notes)*