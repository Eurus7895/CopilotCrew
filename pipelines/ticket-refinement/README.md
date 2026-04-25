# ticket-refinement

**Level 1** pipeline. Refines a thin GitHub issue into a structured,
actionable ticket draft (Title / Summary / User Story / Acceptance
Criteria / Technical Notes / Effort Estimate / Stakeholders / Open
Questions). The output is graded by an isolated evaluator session and
retried with fix instructions on failure (max 3 attempts; escalate
after that).

## Usage

```bash
crew "refine eurus7895/copilotcrew#42"
crew "refine #42"
crew "make ticket #42 ready for sprint planning"
crew --pipeline "issue 42 needs more detail before we work on it"
crew --pipeline --summary "refine #42"
```

## Inputs

* GitHub MCP server declared in the repo-root `.mcp.json` (`github`).
* The signed-in Copilot or GitHub identity.
* A free-text prompt that names a GitHub issue (`org/repo#N` or `#N`).
  When only `#N` is given, the generator picks the most recently active
  repository the signed-in identity has access to.

## Output

* Markdown draft written to
  `~/.crew/outputs/ticket-refinement/<timestamp>-<uid>-attempt{N}.md` —
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
| `schema` | `schemas/refined-ticket.json` |
| `mcp` | `github` |
| `allowed_tools` | `read`, `write`, `mcp` |
| `output_subdir` | `ticket-refinement` |

## Evaluator behaviour

The evaluator runs in a **fresh `CopilotClient`** with a fresh session
and no MCP / no tools — it sees only the draft text and the schema.
Verdicts are strict JSON `{status, issues, summary}`. On `fail`, the
verdict's `fix_instruction` strings are appended to the next generator
prompt. The schema's hardest-to-fake rule is `ac_is_user_facing`: AC
items must read as user-observable behaviour, not "add a retry handler"
implementation bullets — a frequent first-attempt failure mode that the
correction loop fixes by reframing.
