# Changelog — Crew

Completed work, week by week. Future work lives in `ROADMAP.md`.

---

## Day 4-C — GUI interactivity (April 2026)

```
[x] POST /chat route bridging to crew.direct.run_direct, reusing the
    per-scope session cache via crew.conversations; tokens stream
    over the SSE bus as chat_token events
[x] Per-theme chat_turn.html + message-bubble area + composer wiring
    (Warm paper bubbles, Terminal crew>/you> grid, Modernist editorial
    entries under §-rule)
[x] Clickable pinned items: POST /pinned/{kind}/{name} dispatches
    skills (append skill_prompt), agents (swap agent_prompt),
    pipelines (kick off a run), plus POST /pinned/memory → $EDITOR
[x] Visible regenerate stream in the standup card (#standup-progress
    strip listens to pipeline_progress SSE; no backend change)
```

The GUI is no longer read-only: the mockup's chat input and pinned
items now dispatch to real Crew primitives, and the standup
regenerate stream is visible live in each theme. Three increments,
all reusing the existing SSE bus + `crew.streamer.CallbackStreamer`:

1. **Chat input.** The theme-specific input strip ("Tell Crew about
   morning…" in Warm, `crew>` in Terminal, a bottom composer in
   Modernist) becomes a working conversation channel. `POST /chat`
   bridges to `crew.direct.run_direct`, reusing the per-scope session
   cache from `crew/conversations.py`; tokens stream over the existing
   SSE bus; each theme renders a message-bubble area below the
   greeting. Turn rotation respects `CREW_TURN_CAP` exactly like the
   CLI. Pipelines + the evaluator still never resume (principle #2).
2. **Clickable pinned items.** Left-rail entries gain handlers:
   slash-commands (`/debug`) fire the skill as a direct call,
   `agent:coder` opens a fresh chat with the persona active (routes
   through `crew.direct` with `agent_prompt`), pipelines (`/standup`)
   kick off a run gated by the existing concurrency lock,
   `memory.jsonl` opens the facts file in `$EDITOR`.
3. **Visible regenerate stream.** The standup card got a collapsible
   progress strip that listens to the `pipeline_progress` SSE events
   and prints deltas as they arrive.

"Post to #standup" stays disabled until Slack integration lands.

---

## Day 4-B — Streaming + remaining pipelines

```
[x] streamer.py: terminal output + summary mode + GUI callback strategy
[x] ticket-refinement, code-review-routing, release-notes
```

* `crew/streamer.py` consolidates the `on_event` handler that every
  Copilot session used to re-implement (direct mode, pipeline runner,
  evaluator, intent router). One `Streamer` class with three modes:
  `verbose` (stream tokens to stdout — direct / agent / slash),
  `summary` (terse status lines: generating / tool / done N chars —
  pipelines under `--summary`), `silent` (capture-only — evaluator +
  router + GUI). Tool-execution events fan out to optional
  `on_tool_start` / `on_tool_end` callbacks so the pipeline runner
  keeps firing `pre-tool-use` / `post-tool-use` hooks without
  re-implementing the event-type dispatch. Per-delta callbacks fire
  through the optional `on_delta` field — used by the GUI's
  `CallbackStreamer` to publish each token onto the SSE bus.
* `crew --pipeline --summary "…"` is the user-facing flag. The
  generated output file is identical in both modes — `--summary` only
  changes what lands on the terminal.
* Both `crew.direct.run_direct` and `crew.pipeline_runner.run_pipeline`
  accept an optional `streamer=` kwarg. The GUI passes a
  `CallbackStreamer(on_delta_fn=...)` so chat tokens and pipeline
  progress flow over the SSE bus instead of stdout.
* Three new pipelines complete the v1 set of five:
  * `release-notes` (Level 0) — drafts release notes from merged PRs
    between two refs, bucketed Highlights / Features / Fixes /
    Internal-Chores / Contributors.
  * `ticket-refinement` (Level 1) — refines a thin GitHub issue into a
    structured draft (Title / Summary / User Story / AC / Technical
    Notes / Effort / Stakeholders / Open Questions). Evaluator's
    hardest-to-fake rule is `ac_is_user_facing`.
  * `code-review-routing` (Level 1) — recommends ranked reviewers for
    an open PR, citing CODEOWNERS rules or recent PR authorship.
* End-to-end live-data exercise of all five pipelines is moved to
  Day 5 — it needs live MCP credentials and a real team repo.

---

## Day 4-A — Bounded session continuity for chatty modes

```
[x] crew/conversations.py: per-scope session_id cache + rotation log
[x] crew/direct.py: accept session_id, return DirectResult (id + text)
[x] crew/cli.py: --new flag + memory wrapper (zero additional CLI surface)
[x] Summary rotation when CREW_TURN_CAP turns reached (CREW_SUMMARY_MODEL
    selects the summariser model; default: user's current model)
[x] Pipelines + evaluator stay one-shot (runtime guard tests)
```

* **Minimal surface by design.** Users don't manage sessions — they just
  chat. The only user-facing knob is `--new` (forget and start over).
  An earlier draft added `--session NAME`, `--no-memory`, and a
  `crew sessions {list,show,clear}` subcommand; all three were dropped
  as surplus surface.
* **Scope = (mode, agent_or_skill, cwd)** hashed for filesystem safety.
  The readable cwd is stored inside the session value for audit but is
  not user-facing.
* **Slash commands carry per-skill memory.** `scope = ("slash",
  skill_name, cwd)` so `/debug` in projA and `/debug` in projB are
  separate threads.
* **JSONL is rotation input, not a user surface.** Each turn appends
  one row to `~/.crew/conversations/<scope>.jsonl`; rotation reads the
  tail to produce the handoff summary, then writes a `rotated` event
  marker.
* **Pipelines + evaluator NEVER resume.** Principle #2 is non-negotiable.
  Two runtime guard tests assert `session_id` never appears in
  `create_session` kwargs from `pipeline_runner` or the evaluator.

---

## Day 3 — Evaluator + incident-triage (Level 1)

```
[x] evaluator.py: separate CopilotClient factory + verdict parser
[x] pipeline_runner.py Level 1 execution with isolated evaluator
[x] Hook injection: on-eval-fail, on-escalate
[x] Test: evaluator grades in fresh session, correction loop fires
```

* The evaluator receives the generator's output **text** inline, not a
  file path. Its session has no MCP and no permission handler, so it
  cannot read files anyway — passing the path would buy nothing. This
  stays faithful to "fresh eyes, fresh context".
* Evaluator session uses `enable_config_discovery=False`. No MCP, no
  skill, no tools. System message is `evaluator_prompt` plus the
  pipeline's `schema_text`, in `replace` mode.
* Each attempt's output is preserved on disk
  (`~/.crew/outputs/<pipeline>/<ts>-<uid>-attempt{N}.md`) so a failed
  run is auditable. The single per-run plan JSON contains the full
  `attempts` array (per-attempt verdict, output path, timestamps) and
  an `escalated` flag.
* `run_pipeline(config, ...)` dispatches by `config.level` (0 → Level
  0; 1 → Level 1; 2+ → ValueError). The CLI calls `run_pipeline`
  exclusively; `run_level_0` / `run_level_1` stay exported for tests.
* `crew/harness/correction_loop.py` (the SQLite-stage harness ported
  from CopilotHarness) stays dormant — its plan→design→code→review
  contract doesn't fit the generator/evaluator loop. The Day 3 loop
  lives inside `pipeline_runner.run_level_1` instead.

---

## Day 2.5 / 2.75 / 2.8 — Agents, slash commands, skills

Incremental slices landed alongside Day 2 to close the ergonomics gap
before Day 3's evaluator work:

```
[x] agents/<name>.md — standalone persona swaps (--agent NAME + auto-summon)
[x] Intent router upgraded to 3-way (direct / agent / pipeline)
[x] Slash commands invoke skills at skills/<name>/SKILL.md
[x] skill_registry supports multiple search roots (plugin-ready)
[x] skills/debug/ — first shipped skill
[x] /help built-in: zero-LLM registry listing
```

---

## Day 2 — Intent router + standup (Level 0)

```
[x] intent_router.py: classify direct vs pipeline:{name}
[x] PIPELINE_REGISTRY with descriptions for router matching
[x] Load pipeline from pipelines/standup/ directory
[x] pipeline_runner.py Level 0 execution
[x] Hook injection points: session-start, pre-tool-use, post-tool-use
[x] Test: crew "standup prep" → routes to pipeline → output file
[x] Test: crew "what time is it?" → routes to direct → inline answer
[x] --direct and --pipeline override flags work
```

---

## Day 1 — SDK smoke test + direct mode

```
[x] Copilot SDK quickstart: one agent, one prompt, prints response
[x] Copy harness core from CopilotHarness (6 files), update paths
[x] Implement direct mode: crew "hello" → streamed response
[x] Implement load_agent_md(): parse frontmatter + markdown body
[x] Direct mode works with MCP (crew "how many open PRs?")
```
