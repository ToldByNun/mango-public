"""A3: grounded_ws matching, edit recovery feedback, soft stall + continue."""

from __future__ import annotations

from mango_agent.agent import Agent, _STALL_ESCALATE, _STALL_LIMIT
from mango_agent.flags import edit_match_mode, stall_mode
from mango_runtime.types import CompletionResult
from mango_tools.fuzzy_edit import apply_replace
from mango_tools.types import ToolCall, ToolResult


class _DummyModel:
    def complete(self, *args, **kwargs):
        return CompletionResult(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)


def test_grounded_ws_allows_collapsed_whitespace(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_EDIT_MATCH_MODE", "grounded_ws")
    assert edit_match_mode() == "grounded_ws"
    updated, count, kind = apply_replace(
        "def foo():\n    return  a\n",
        "return a",
        "return b",
        allow_fuzzy=False,
        allow_whitespace=True,
    )
    assert kind == "whitespace"
    assert "return b" in updated
    assert count == 1


def test_soft_stall_never_auto_stops(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_STALL_MODE", "soft")
    assert stall_mode() == "soft"

    class _Engine:
        def __init__(self) -> None:
            self.feedback = ""

        def set_verification_feedback(self, text: str) -> None:
            self.feedback = text

    agent = Agent(model_runner=_DummyModel(), require_tools=True)
    engine = _Engine()
    same = "The bot is complete and ready."
    for _ in range(_STALL_LIMIT + 3):
        assert agent._note_stall(same, engine) is False
    assert agent._metric_stall_triggered is True


def test_hard_stall_stops_unless_continue(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_STALL_MODE", "hard")
    assert stall_mode() == "hard"

    class _Engine:
        def set_verification_feedback(self, text: str) -> None:
            return None

    agent = Agent(model_runner=_DummyModel(), require_tools=True)
    engine = _Engine()
    same = "stuck forever without tools"
    for _ in range(_STALL_ESCALATE):
        agent._note_stall(same, engine)
    assert agent._note_stall(same, engine) is False
    # Reach hard stop
    while not agent._note_stall(same, engine):
        pass
    agent.continue_after_stall()
    assert agent._note_stall(same, engine) is False


def test_identical_edit_fail_recovery_feedback() -> None:
    agent = Agent(model_runner=_DummyModel(), require_tools=True)

    class _Engine:
        def __init__(self) -> None:
            self.feedback = ""

        def set_verification_feedback(self, text: str) -> None:
            self.feedback = text

        @property
        def state(self):
            return type("S", (), {"verification_feedback": self.feedback})()

    engine = _Engine()
    call = ToolCall(
        name="edit_file",
        arguments={"path": "a.py", "old_string": "x", "new_string": "y"},
        raw="",
        start=0,
        end=0,
    )
    fail = ToolResult(success=False, tool_name="edit_file", error="old_string not found", call=call)
    agent._feedback_failed_tools(engine, [fail])
    agent._feedback_failed_tools(engine, [fail])
    assert "Preferred next tools: read_file, write_file" in engine.feedback
    agent._feedback_failed_tools(engine, [fail])
    assert agent._metric_stall_triggered is True
