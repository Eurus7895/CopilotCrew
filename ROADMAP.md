# Roadmap — Crew

What's next, what's known-broken, and the long-term evolution path.
Completed work lives in `CHANGELOG.md`.

**Day-N vs Phase-N.** "Day" refers to the v1 build sprint sequence
(Day 1 → Day 5); each Day is a tight, dated milestone. "Phase" refers
to post-v1 evolution buckets (Phase 2 onward) with no fixed dates —
they exist to record decisions made now about future work, not
commitments. Day 5 is the final v1 Day; everything beyond it is a
Phase.

---

## Day 5 — Hardening + first team member (next)

```
[ ] Baseline checks in session-start hook (MCP alive, last output intact)
[ ] crew logs    — tail SQLite audit log
[ ] crew status  — show registries, cached sessions, last run per pipeline
[ ] crew resume  — explicitly resume a named scope
[ ] README: install in 5 minutes
[ ] Test all 5 pipelines end-to-end on real team data
    (moved from Day 4-B; needs live MCP creds + a real team repo)
[ ] Give to 1 team member. Watch. Take notes.
```

---

## Known TODOs

* Slack integration. The GUI's "Post to #standup" button is wired
  only to the UI; the backend stub raises until Slack is connected.
* Live-data shakedown of `release-notes`, `ticket-refinement`, and
  `code-review-routing` against a real team repo (Day 5 task).
* `crew/harness/correction_loop.py` is dormant. Either retire it
  once cross-stage state is needed elsewhere, or document its
  intended re-use case so future maintainers don't delete it.
* `context_budget` enforcement per pipeline — designed (see
  Architecture > Context Management) but not implemented.

---

## Evolution Path

Designed now. Not building in v1.

### Phase 2 — Plugin + Pipeline Install (Month 2+)

`crew install` = copy a directory into the project. A plugin bundles
multiple skills (and optionally agents, pipelines, hooks) under
`plugins/<name>/` with a `plugin.yaml` manifest and nested `skills/`,
`agents/`, `pipelines/` directories. The v1 file formats ARE the
install formats — no migration. The skill registry already supports
multiple search roots (local `skills/` + any `plugins/*/skills/`),
so activating plugin discovery is a registry-wiring change, not a
format redesign.

### Phase 3 — Auto-Invoke Skills (Month 3+)

Skills register trigger descriptions in frontmatter. LLM decides
which to load — no classifier, no regex. Same mechanism as Claude
Code skills. Day 2.8 shipped explicit skill invocation via
`/skill-name`; Phase 3 adds the auto-invoke path without changing
the skill file format.

### Phase 4 — Custom Hooks (Month 3+)

Hooks become executable: `type: command` (shell), `type: http`
(webhook), `type: agent` (spawn agent to handle event). Follows
Claude Code hook types.

### Phase 5 — Plugin Marketplace (Month 6+)

GitHub repo of validated plugins. `crew install
name@crew-plugins-official` fetches and installs.
Plugin-as-directory format = marketplace entry format (see Phase 2).
No migration.

### Phase 6 — SSO / Enterprise Auth (Month 4+)

Only after team adoption proven.

### Phase 7 — Desktop GUI (shipped alongside Day 4-A; see CHANGELOG)

The dashboard (`crew gui`) is live. Future GUI work folds into
Phase 8 (Slack) and incremental theme/UX polish; no GUI architecture
changes are pending.

### Phase 8 — Slack integration (planned)

Wire the GUI's "Post to #standup" button to a real Slack webhook;
add `slack-mention` cards backed by a real Slack source instead of
the JSONL stub. Gates: a maintained team Slack workspace + a bot
token policy. CLI side: `crew /standup --post` flag.

---

## Risks

| Risk | Probability | Mitigation |
|---|---|---|
| SDK Public Preview breaks | Medium | BYOK Anthropic adapter |
| MCP unreliable | Medium | Graceful degradation |
| Intent router misroutes | High initially | Slash commands bypass router |
| Evaluator too strict/loose | Medium | Start lenient, tune after baseline |
| Team doesn't adopt | Medium | Ship Day 5, watch, don't assume |
| Premature Level 2 | High risk | Promotion checklist mandatory |
| Claude Code ships team workflows | Low-Medium | Cross-LLM via BYOK |

---

## Not Building in v1

```
[no] Level 2 pipelines         [no] Pipeline marketplace
[no] Auto-invoke skills        [no] Executable hooks (beyond Python scripts)
[no] SSO / enterprise auth     [no] Cloud deployment
[no] Multi-user sessions       [no] More than 5 pipelines
[no] context_budget enforcement
```

The local web dashboard was originally listed here as "not in v1" but
shipped alongside Day 4-A. See **Phase 7** above and CHANGELOG.
