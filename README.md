# Crew

Terminal-native virtual assistant powered by the Copilot SDK. See `CLAUDE.md`
for the full design doc and `AGENTS.md` for session-start orientation.

## Status

**Day 2.75 of the build order** — slash commands (`/name`) for zero-cost
deterministic dispatch, on top of Day 2.5's 3-way intent router
(direct / agent / pipeline), the standalone `agents/` directory, Day 2's
pipeline runner + hook registry, and the `daily-standup` pipeline.

## Install

```bash
pip install -e ".[dev]"
```

`github-copilot-sdk>=0.2.2` ships platform wheels that bundle the `copilot`
CLI binary, so pip picks the right wheel for your OS/arch and you get the
runtime with no extra steps. Override with `COPILOT_CLI_PATH` to point at an
existing install.

## Authentication

Direct mode needs either a GitHub Copilot subscription or a BYOK provider
key. Two options:

1. **GitHub Copilot** — run `copilot` once and sign in; the SDK picks up the
   cached credential automatically on the next `crew` invocation.
2. **BYOK** — set `GITHUB_TOKEN`, or pass a `ProviderConfig` (Anthropic,
   Azure, custom endpoint) to the SDK. See the Copilot SDK docs.

## Usage

```bash
crew "what is 2+2?"                # router → direct mode
crew "fix the flaky test in foo.py" # router → agent:coder (auto-summoned)
crew "standup prep"                # router → daily-standup pipeline
crew /daily-standup                # slash command: zero-cost, skips the router
crew /coder "refactor X"           # slash command: dispatches to agents/coder.md
crew --direct "summarise this"     # force direct mode (skips the router)
crew --agent coder "refactor X"    # force a specific standalone agent
crew --pipeline "standup prep"     # force pipeline mode (router picks which)
```

**Slash commands** (`/<name>`) match against the pipeline registry first,
then the standalone agent registry. They bypass the intent router entirely
— zero LLM cost for the dispatch. Unknown names exit with code 2 and list
the available commands.

**Agents** (`agents/*.md`) are persona swaps: one LLM call like direct
mode, but with the agent's system prompt. No output file, no plan JSON.
The intent router auto-summons the best-matching agent based on the
frontmatter `description`. See `agents/coder.md` for the format.

**Pipelines** are governed workflows. Runs write a Markdown summary to
`~/.crew/outputs/<pipeline>/<timestamp>.md` and a run manifest to
`~/.crew/plans/<session-id>.json`. See `pipelines/standup/README.md` for the
first pipeline.

## Tests

```bash
python3 -m pytest -q
```
