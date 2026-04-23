import asyncio
import logging

from crew import evaluator
from fake_copilot import make_fake_copilot_client


def _run(coro):
    return asyncio.run(coro)


def test_parse_verdict_happy(monkeypatch) -> None:
    factory = make_fake_copilot_client(
        reply='{"status":"pass","issues":[],"summary":"ok"}'
    )
    monkeypatch.setattr(evaluator, "CopilotClient", factory)

    verdict = _run(evaluator.evaluate("hello", "Be strict."))
    assert verdict.status == "pass"
    assert verdict.issues == []
    assert verdict.summary == "ok"
    assert verdict.fix_instructions == []


def test_parse_verdict_handles_issues(monkeypatch) -> None:
    factory = make_fake_copilot_client(
        reply='{"status":"fail","summary":"missing summary",'
        '"issues":[{"severity":"major","description":"no Summary heading",'
        '"fix_instruction":"Add a `## Summary` heading."}]}'
    )
    monkeypatch.setattr(evaluator, "CopilotClient", factory)

    verdict = _run(evaluator.evaluate("hello", "Be strict."))
    assert verdict.status == "fail"
    assert len(verdict.issues) == 1
    assert verdict.issues[0].severity == "major"
    assert verdict.fix_instructions == ["Add a `## Summary` heading."]


def test_parse_verdict_invalid_json_falls_back(monkeypatch, caplog) -> None:
    factory = make_fake_copilot_client(reply="not json at all")
    monkeypatch.setattr(evaluator, "CopilotClient", factory)

    with caplog.at_level(logging.WARNING, logger="crew.evaluator"):
        verdict = _run(evaluator.evaluate("hello", "Be strict."))

    assert verdict.status == "fail"
    assert verdict.issues == []
    assert verdict.fix_instructions == ["not json at all"]
    assert any("non-JSON" in record.message for record in caplog.records)


def test_evaluator_session_kwargs_are_isolated(monkeypatch) -> None:
    factory = make_fake_copilot_client(
        reply='{"status":"pass","issues":[],"summary":"ok"}'
    )
    monkeypatch.setattr(evaluator, "CopilotClient", factory)

    _run(
        evaluator.evaluate(
            "OUTPUT TEXT", "You are an evaluator.", schema_text="must contain Summary"
        )
    )

    client = factory.clients[-1]
    session = client.sessions[-1]
    kwargs = session.kwargs
    assert kwargs["enable_config_discovery"] is False
    # Evaluator runs without any tool/permission handler — strictly read-only.
    assert "on_permission_request" not in kwargs
    system = kwargs["system_message"]
    assert system["mode"] == "replace"
    assert "must contain Summary" in system["content"]
    # The user message wraps the output text in the documented envelope.
    assert any("<<<OUTPUT>>>" in s and "OUTPUT TEXT" in s for s in session.sent)


def test_evaluator_does_not_stream_to_stdout(monkeypatch, capsys) -> None:
    factory = make_fake_copilot_client(
        reply='{"status":"pass","issues":[],"summary":"ok"}'
    )
    monkeypatch.setattr(evaluator, "CopilotClient", factory)

    _run(evaluator.evaluate("hello", "Be strict."))
    captured = capsys.readouterr()
    assert captured.out == ""


def test_unknown_status_treated_as_fail(monkeypatch) -> None:
    factory = make_fake_copilot_client(
        reply='{"status":"maybe","issues":[],"summary":"hmm"}'
    )
    monkeypatch.setattr(evaluator, "CopilotClient", factory)

    verdict = _run(evaluator.evaluate("hello", "Be strict."))
    assert verdict.status == "fail"
