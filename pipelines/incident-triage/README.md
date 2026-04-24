# incident-triage

**Level 1** pipeline. Collects evidence from recent GitHub activity (commits,
CI runs, releases) for the time window around a reported incident, then
produces a structured triage report (Summary / Timeline / Suspected Causes
/ Next Actions). The output is graded by an isolated evaluator session and
retried with fix instructions on failure (max 3 attempts; escalate after
that).

## Usage

```bash
crew "triage the API outage we saw at 14:00"
crew "investigate the failing deploy on payments-service"
crew --pipeline "auth service is returning 500s"
```

## Inputs

* GitHub MCP server declared in the repo-root `.mcp.json` (`github`).
* The signed-in Copilot or GitHub identity.
* A free-text incident description in the user prompt.

## Output

* Markdown report written to
  `~/.crew/outputs/incident-triage/<timestamp>-<uid>-attempt{N}.md` —
  one file per generator attempt.
* Run manifest at `~/.crew/plans/<session-id>.json` containing every
  attempt's verdict (`status`, `summary`, `issues`) and an `escalated`
  flag.

## Config

| Field | Value |
|---|---|
| `level` | `1` |
| `agent` | `agents/generator.md` |
| `evaluator` | `agents/evaluator.md` |
| `schema` | `schemas/incident-report.json` |
| `mcp` | `github` |
| `allowed_tools` | `read`, `shell`, `mcp` |
| `output_subdir` | `incident-triage` |

## Evaluator behaviour

The evaluator runs in a **fresh `CopilotClient`** with a fresh session and
no MCP / no tools — it sees only the report text and the schema. Verdicts
are strict JSON `{status, issues, summary}`. On `fail`, the verdict's
`fix_instruction` strings are appended to the next generator prompt. On
`escalate` (structurally broken output), the loop short-circuits without
further retries. Hooks `on-eval-fail` (per failed attempt) and
`on-escalate` (once on exhaustion or hard escalation) fire so external
observers can react.
