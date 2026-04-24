"""Local web dashboard for Crew.

Optional extra. Install with ``pip install 'crew[gui]'``. Launched via
``crew gui``. The dashboard is a thin read-only viewer over the existing
async core plus a launcher for the daily-standup pipeline — no new
backend concepts. Aspirational UI elements (timeline, remembered facts,
PR/Slack cards) read from JSONL files under ``~/.crew/`` so future
hooks/pipelines can populate them without GUI code changes.
"""

from __future__ import annotations
