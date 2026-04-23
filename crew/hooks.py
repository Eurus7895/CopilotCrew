"""In-process hook registry for pipeline lifecycle events.

Per CLAUDE.md "Architecture / 4. Hooks": hooks are deterministic code at
lifecycle points. v1 keeps them in-process Python callables — Day 3+ adds
the Claude-Code-style `hooks.json` loader and shell/http/agent hook types.

The event names follow CLAUDE.md's table (session-start, pre-tool-use,
post-tool-use, on-eval-fail, on-escalate) plus `post-run` which corresponds
to Claude Code's `Stop` lifecycle. `on-eval-fail` / `on-escalate` are
declared here so Day 3 can register against them without re-plumbing the
registry.

Hooks are fire-and-forget: exceptions raised by a hook are logged and
swallowed so a buggy hook cannot crash the run.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Literal

HookEvent = Literal[
    "session-start",
    "pre-tool-use",
    "post-tool-use",
    "on-eval-fail",
    "on-escalate",
    "post-run",
]

HookFn = Callable[..., None]

_EVENTS: tuple[HookEvent, ...] = (
    "session-start",
    "pre-tool-use",
    "post-tool-use",
    "on-eval-fail",
    "on-escalate",
    "post-run",
)

_log = logging.getLogger("crew.hooks")

_REGISTRY: dict[HookEvent, list[HookFn]] = {event: [] for event in _EVENTS}


def _default_stderr_logger(event: HookEvent) -> HookFn:
    def _fn(**ctx: Any) -> None:
        summary = " ".join(f"{k}={v!r}" for k, v in ctx.items())
        sys.stderr.write(f"[crew.hook {event}] {summary}\n")

    _fn.__name__ = f"_stderr_logger[{event}]"
    return _fn


def _install_defaults() -> None:
    for event in _EVENTS:
        _REGISTRY[event].append(_default_stderr_logger(event))


_install_defaults()


def register(event: HookEvent, fn: HookFn) -> None:
    if event not in _REGISTRY:
        raise ValueError(f"Unknown hook event {event!r}. Valid: {_EVENTS}")
    _REGISTRY[event].append(fn)


def unregister(event: HookEvent, fn: HookFn) -> None:
    if event not in _REGISTRY:
        raise ValueError(f"Unknown hook event {event!r}. Valid: {_EVENTS}")
    try:
        _REGISTRY[event].remove(fn)
    except ValueError:
        pass


def fire(event: HookEvent, **ctx: Any) -> None:
    if event not in _REGISTRY:
        raise ValueError(f"Unknown hook event {event!r}. Valid: {_EVENTS}")
    for fn in list(_REGISTRY[event]):
        try:
            fn(**ctx)
        except Exception as exc:
            _log.warning("hook %s raised %s: %s", event, type(exc).__name__, exc)


def clear(event: HookEvent | None = None) -> None:
    """Test helper: drop all registered hooks. Re-installs stderr defaults."""
    if event is None:
        for key in _REGISTRY:
            _REGISTRY[key].clear()
        _install_defaults()
        return
    if event not in _REGISTRY:
        raise ValueError(f"Unknown hook event {event!r}. Valid: {_EVENTS}")
    _REGISTRY[event].clear()
    _REGISTRY[event].append(_default_stderr_logger(event))


def events() -> tuple[HookEvent, ...]:
    return _EVENTS
