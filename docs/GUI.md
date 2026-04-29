# GUI — Crew

`crew gui` opens a native desktop window (PyWebView) showing a
three-pane dashboard. Internally a FastAPI + Jinja2 + HTMX app runs on
an ephemeral localhost port inside the app process; the user-visible
surface is a PyWebView window pointing at it. No browser, no URL to
remember, no visible server.

The CLI remains primary. The GUI is an optional `[gui]` extra.

---

## Install

```bash
pip install -e ".[gui]"
```

The `[gui]` extra pulls in FastAPI, uvicorn, Jinja2, sse-starlette, and
PyWebView. PyWebView uses the OS's native webview — usually already
installed. On Linux you may need `sudo apt install libwebkit2gtk-4.1-0`
(or `libwebkit2gtk-4.0-37` on older distros).

---

## Run

```bash
crew gui                        # desktop window, ephemeral port
crew gui --model gpt-4o         # status-bar model label override
crew gui --no-window --open     # headless / CI / screencast: run the
                                # server on 127.0.0.1:8765 and open
                                # the system browser
```

---

## Ship as a clickable app

Teammates shouldn't need a Python toolchain. Package the GUI as a
double-clickable bundle with PyInstaller:

```bash
pip install -e '.[gui,package]'
python packaging/build.py
```

Outputs land in `dist/`:

- `dist/Crew.app` — macOS bundle
- `dist/Crew/Crew.exe` — Windows
- `dist/Crew/Crew` — Linux

See `packaging/README.md` for icons, code-signing, and a cross-platform
GitHub Actions matrix.

---

## What's in the window

The window is interactive: typing into the chat composer fires
`POST /chat` (bridges to direct mode, streams the reply in a bubble
that fills in live), clicking a pinned `/standup` / `/debug` /
`agent:coder` / `memory.jsonl` dispatches the right primitive
(pipeline / skill / agent / `$EDITOR`), and the standup "Regenerate"
button reveals a progress strip that streams the pipeline's output
as it arrives.

### Three swappable design languages

Picked from `/settings` (cookie-persisted):

- **Warm · Workspace** (default) — warm neutrals, paper cards, polaroid
  avatar, "A gentle note" panel, chat-style "Tell Crew about…" input.
- **Terminal · Operator** — tmux-style console, phosphor amber on black,
  ASCII section rules, vim keybinding hints, `crew>` prompt.
- **Modernist · Swiss** — Archivo 900 + signal-red, giant `01/05`
  numerals, `§01` section markers, "BY THE NUMBERS" right rail.

### Three panes

- **Left rail** — pinned slash commands / agents / pipelines drawn from
  the real registries, plus a day timeline.
- **Center** — greeting, cards for overnight PR activity and Slack
  mentions, the latest daily-standup draft (live from
  `~/.crew/outputs/daily-standup/`), and an action row. *Post to
  #standup* is disabled until Slack integration lands; *Regenerate*
  re-runs the `daily-standup` pipeline with stdout captured into an SSE
  bus; *Edit draft* opens the output in `$EDITOR`; *Skip today*
  deletes the latest draft.
- **Right rail** — context panel. Per-theme content: Warm shows recent
  observations + a gentle note, Terminal shows `~/CONTEXT` kv table +
  `~/MEMORY.JSONL`, Modernist shows "BY THE NUMBERS" stats + editorial
  observations.

Aspirational data (timeline events, remembered facts, PR/Slack cards,
working-on chips) read from JSONL files seeded into `~/.crew/gui/` and
`~/.crew/memory.jsonl` on first launch. Edit them by hand or let future
hooks/pipelines append — the window picks up changes on the next
request. Internal server binds `127.0.0.1` only; no auth in v1.

For the rendering pipeline, file layout, and streaming bridge, see
[`ARCHITECTURE.md` § GUI Rendering](./ARCHITECTURE.md#gui-rendering).
