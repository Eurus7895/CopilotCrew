"""Crew harness — ported from Eurus7895/CopilotHarness@dev.

Dormant in v1 direct mode; activated by Day 2+ pipelines (see CLAUDE.md
"Build Order"). All cross-module imports are package-relative; path constants
read from CREW_AGENTS_DIR / CREW_SKILLS_DIR / CREW_DB_PATH env vars (Day 2
will refactor to explicit pipeline_dir arguments).
"""
