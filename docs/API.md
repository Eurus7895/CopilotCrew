# API Reference — Crew

Frontmatter fields, hooks, MCP server config, and the policy engine.
For prose explanations see `./ARCHITECTURE.md`.

---

## Agent Frontmatter

Markdown agents (`agents/<name>.md`, `pipelines/<name>/agents/*.md`)
take YAML frontmatter between two `---` lines. Body is the system
prompt.

```markdown
---
name: incident-generator
description: Collects evidence and produces structured incident reports
model: gpt-4.1
maxTurns: 30
disallowedTools: Write, Edit
skills: [incident-response]
isolation: false
---

You are an incident response analyst. ...
```

| Field | Purpose | Crew usage |
|---|---|---|
| `name` | Agent identifier | Pipeline routing |
| `description` | When to invoke this agent | Intent router matching |
| `model` | Which model to use | Copilot SDK model selection |
| `maxTurns` | Max tool call iterations | Prevents infinite loops |
| `allowedTools` | Tools this agent may use | Whitelist (mutually exclusive with `disallowedTools`) |
| `disallowedTools` | Tools this agent cannot use | Principle of least privilege |
| `skills` | Auto-load these skills | Skill injection per agent |
| `isolation` | Run in isolated context | Evaluator always isolated |

---

## Skill Frontmatter

Skills (`skills/<name>/SKILL.md`, `pipelines/<name>/skills/SKILL.md`)
take YAML frontmatter; the body is appended to the session system
message when the skill is invoked.

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

When a skill loads, it (1) injects instructions as new context, (2)
may modify allowed tools for that session, (3) may reference scripts
or data files in `skills/<name>/scripts/`.

---

## Slash Commands

Markdown command files in `.claude/commands/<name>.md`:

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

Slash invocation: `/standup`, `/triage "API errors"`, `/refine PROJ-123`.
Bypasses the intent router (zero LLM cost).

---

## Hooks Reference

Hooks tie deterministic Python code to specific lifecycle moments.
Registered in `crew/hooks.py` (in-process registry for v1).

| Hook | Claude Code equivalent | Type | Fires |
|---|---|---|---|
| `session-start` | `SessionStart` | `command` | Before pipeline run |
| `pre-tool-use` | `PreToolUse` | `command` | Before every tool call |
| `post-tool-use` | `PostToolUse` | `command` | After every tool call |
| `on-eval-fail` | (custom) | `command` | Evaluator rejects output |
| `on-escalate` | (custom) | `command` | Max retries exceeded |
| `post-run` | (custom) | `command` | Pipeline run finished successfully |

### Hook config format

Adapted from Claude Code `hooks.json`:

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

---

## MCP Server Config

Same schema as Claude Code's `.mcp.json`. Each pipeline can declare
its own MCP dependencies; global MCP config lives at project root.

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

## Pipeline Manifest (`pipeline.yaml`)

```yaml
name: incident-triage
level: 1                        # 0 | 1 | (2 reserved)
description: Triage an incident from a thin description
mcp_servers: [github, jira]
agents:
  generator: agents/generator.md
  evaluator: agents/evaluator.md
schemas:
  output: schemas/incident-report.json
correction:
  max_retries: 3                # before on-escalate fires
```

Loaded by `crew/pipeline_registry.py`; resolved into a
`PipelineConfig` object. Discovery is automatic — drop a directory
under `pipelines/` and the registry picks it up on next run.

---

## Direct Mode API

```python
from crew.direct import run_direct, DirectResult

result: DirectResult = await run_direct(
    user_input,
    *,
    session_id=None,         # None → fresh; cached id → resume
    agent_prompt=None,       # set to swap the system message (--agent)
    skill_prompt=None,       # set to append a skill (slash commands)
    streamer=None,           # crew.streamer.Streamer instance
)
# result.session_id, result.assistant_text
```

The CLI wraps this through `crew/conversations.py`, which handles
the per-scope session cache and summary rotation transparently.
Pipelines + the evaluator never call `run_direct` and never receive
a `session_id` (principle #2).

---

## Streamer

`crew.streamer.Streamer` consolidates SDK event handling. Three modes:

| Mode | Output | Typical caller |
|---|---|---|
| `verbose` | Stream tokens to stdout | direct / agent / slash |
| `summary` | Terse status lines (generating / tool / done N chars) | `crew --pipeline --summary` |
| `silent` | Capture-only, no stdout | evaluator + router + GUI |

Named subclasses:

* `TerminalStreamer` — verbose, stdout
* `SummaryStreamer` — summary, stdout
* `CallbackStreamer(on_delta_fn=...)` — silent + per-delta callback;
  used by the GUI to push tokens onto the SSE bus

Tool-execution events fan out through optional `on_tool_start` /
`on_tool_end` callbacks so the pipeline runner can fire
`pre-tool-use` / `post-tool-use` hooks without re-implementing the
event-type dispatch.
