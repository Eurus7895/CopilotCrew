# release-notes

**Level 0** pipeline. Drafts release notes from merged pull requests
between two refs (defaults to "previous release tag → HEAD"). Groups
each PR into Features / Fixes / Internal-Chores, picks up to three
Highlights, and lists contributors.

## Usage

```bash
crew "release notes for v2.1"
crew "draft release notes since v1.5.0"
crew "release notes for the next release"
crew --pipeline "release notes"
crew --pipeline --summary "release notes for v2.1"
```

The router matches on intent — `crew "release notes for v2.1"` will
land here without `--pipeline`. The `--summary` flag swaps the live
token stream for terse status lines (useful for cron / CI).

## Inputs

* GitHub MCP server declared in the repo-root `.mcp.json` (`github`).
* The signed-in Copilot or GitHub identity.
* A target release reference in the user prompt — a tag, a branch, a
  `vA..vB` range, or `since vX`. If absent, the generator targets
  `HEAD` since the most recent release tag.

## Output

* Markdown notes written to
  `~/.crew/outputs/release-notes/<timestamp>.md`.
* Run manifest at `~/.crew/plans/<session-id>.json`.

## Config

| Field | Value |
|---|---|
| `level` | `0` |
| `agent` | `agents/generator.md` |
| `mcp` | `github` |
| `allowed_tools` | `read`, `mcp` |
| `output_subdir` | `release-notes` |

No evaluator: release-notes is Level 0 because the team review is the
evaluator — the draft is meant to be edited before publishing. Promote
to Level 1 only after observing repeated drafts that need the same
correction.
