# Crew

Terminal-native virtual assistant powered by the Copilot SDK. See `CLAUDE.md`
for the full design doc and `AGENTS.md` for session-start orientation.

## Status

**Day 2 of the build order** — intent router + Level 0 pipeline runner +
hook injection points, plus the `daily-standup` pipeline. Direct mode,
harness port, and agent loader from Day 1 still apply.

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
crew "standup prep"                # router → daily-standup pipeline
crew --direct "summarise this"     # force direct mode (skips the router)
crew --pipeline "standup prep"     # force pipeline mode (router picks which)
```

Pipeline runs write a Markdown summary to
`~/.crew/outputs/<pipeline>/<timestamp>.md` and a run manifest to
`~/.crew/plans/<session-id>.json`. See `pipelines/standup/README.md` for the
first pipeline.

## Tests

```bash
python3 -m pytest -q
```
