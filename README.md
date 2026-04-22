# Crew

Terminal-native virtual assistant powered by the Copilot SDK. See `CLAUDE.md`
for the full design doc and `AGENTS.md` for session-start orientation.

## Status

**Day 1 of the build order** — direct mode + harness port + agent loader.

## Install

```bash
pip install -e ".[dev]"
```

The Copilot SDK is pulled from `github/copilot-sdk` (Python subdirectory). Direct
mode requires the bundled Copilot CLI binary — install a platform-specific
wheel of `github-copilot-sdk`, or set `COPILOT_CLI_PATH` to point at an
existing `copilot` CLI install.

## Usage

```bash
crew "what is 2+2?"                # direct mode (router defaults here in v1)
crew --direct "summarise this"     # force direct mode
crew --pipeline "..."              # Day 2+ — currently exits with a notice
```

## Tests

```bash
python3 -m pytest -q
```
