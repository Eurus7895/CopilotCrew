# code-review-routing (Level 1)

Given a PR, names the best reviewers with concrete rationale. Reads
CODEOWNERS, recent touches on the files the PR changes, and PR labels via
the GitHub MCP server. Graded by an isolated evaluator that rejects thin
handwaving ("is a senior dev") in favour of specific signals ("owns
`crew/harness/`, last 4 commits there").

## Usage

```bash
crew "who should review eurus7895/CopilotCrew#47"
crew "route review for copilot-sdk#421"
```

Outputs at `~/.crew/outputs/code-review-routing/<timestamp>-<uid>-attemptN.md`.
Plan manifests at `~/.crew/plans/<session>.json`.
