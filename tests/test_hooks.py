from crew import hooks


def setup_function() -> None:
    hooks.clear()


def teardown_function() -> None:
    hooks.clear()


def test_fire_invokes_registered_callback() -> None:
    received: list[dict] = []

    hooks.register("session-start", lambda **ctx: received.append(ctx))
    hooks.fire("session-start", session_id="abc", pipeline="p")

    assert {"session_id": "abc", "pipeline": "p"} in received


def test_fire_swallows_exceptions() -> None:
    calls: list[str] = []

    def bad(**_ctx):
        raise RuntimeError("boom")

    def good(**_ctx):
        calls.append("good")

    hooks.register("post-run", bad)
    hooks.register("post-run", good)

    hooks.fire("post-run", session_id="s")

    assert calls == ["good"]


def test_unregister_removes_listener() -> None:
    received: list[str] = []

    def listener(**_ctx):
        received.append("hit")

    hooks.register("session-start", listener)
    hooks.unregister("session-start", listener)
    hooks.fire("session-start", session_id="s")

    assert received == []


def test_register_rejects_unknown_event() -> None:
    import pytest

    with pytest.raises(ValueError):
        hooks.register("bogus-event", lambda **_ctx: None)  # type: ignore[arg-type]


def test_all_declared_events_can_fire() -> None:
    hits: list[str] = []

    for event in hooks.events():
        hooks.register(event, lambda event=event, **_ctx: hits.append(event))
        hooks.fire(event, session_id="s")

    assert set(hits) == set(hooks.events())
