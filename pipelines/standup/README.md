# daily-standup

Level 0 pipeline. Generates a concise daily standup for the signed-in
GitHub user from the last 24 hours of activity (PRs, reviews, commits).

## Usage

```bash
crew "standup prep"         # router → daily-standup
crew "daily standup"        # router → daily-standup
crew --pipeline "standup"   # force pipeline mode (router still picks)
```

## Inputs

* GitHub MCP server declared in the repo-root `.mcp.json` (`github`).
* The signed-in Copilot or GitHub identity.

## Output

* Markdown summary written to
  `~/.crew/outputs/daily-standup/<timestamp>.md`.
* Run manifest at `~/.crew/plans/<session-id>.json`.

## Config

`pipeline.yaml` declares `level: 0`, the MCP servers to attach, and the
agent to load. The system prompt lives in `agents/generator.md`.
