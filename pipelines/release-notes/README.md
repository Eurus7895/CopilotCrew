# release-notes (Level 0)

Produces a markdown changelog for the repo the user is working on. Driven by
the GitHub MCP server — lists PRs merged between two tags, groups them by
conventional-commit kind, and credits authors.

## Usage

```bash
crew "release notes since v0.4.2"
crew --pipeline "release notes"
```

Output lands at `~/.crew/outputs/release-notes/<timestamp>-<uid>.md`.

No evaluator — team feedback is the evaluator. If the format drifts, tighten
`agents/generator.md` and re-run.
