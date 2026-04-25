# code-review-routing

**Level 1** pipeline. Recommends reviewers for an open pull request,
ranked by file-overlap and CODEOWNERS coverage. Each recommendation
comes with a one-line rationale citing either a CODEOWNERS rule or a
recent PR the reviewer authored or reviewed against a changed file.
The output is graded by an isolated evaluator session and retried with
fix instructions on failure (max 3 attempts; escalate after that).

## Usage

```bash
crew "who should review PR-421"
crew "find reviewers for eurus7895/copilotcrew#42"
crew "route review for #42"
crew --pipeline "PR 42 needs reviewers"
crew --pipeline --summary "who should review #42"
```

## Inputs

* GitHub MCP server declared in the repo-root `.mcp.json` (`github`).
* The signed-in Copilot or GitHub identity.
* A free-text prompt that names a pull request (`org/repo#N` or `#N`).
  When only `#N` is given, the generator picks the most recently active
  repository the signed-in identity has access to.

## Output

* Markdown recommendation written to
  `~/.crew/outputs/code-review-routing/<timestamp>-<uid>-attempt{N}.md` —
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
| `schema` | `schemas/review-routing.json` |
| `mcp` | `github` |
| `allowed_tools` | `read`, `mcp` |
| `output_subdir` | `code-review-routing` |

## Evaluator behaviour

The evaluator runs in a **fresh `CopilotClient`** with a fresh session
and no MCP / no tools — it sees only the recommendation text and the
schema. The hardest-to-fake rule is `every_reviewer_has_rationale`:
"@alice — knows this code" is not enough; the rationale must name a
CODEOWNERS rule (with file glob) or a specific PR number, which the
correction loop pushes the generator to add when the first attempt
hand-waves.
