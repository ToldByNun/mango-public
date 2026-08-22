from __future__ import annotations

from mango_agent.agent import Agent
from mango_runtime.types import CompletionResult


class _DummyModel:
    def complete(self, *args, **kwargs):
        return CompletionResult(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)


def test_action_tools_keep_read_file_when_tests_failing() -> None:
    agent = Agent(model_runner=_DummyModel(), require_tools=True, use_tool_grammar=True)
    agent._acted_once = True
    agent._task_wants_tests = True
    agent._ran_tests_ok = False
    agent._run_tests_failures = 2
    agent._prefer_read_file = True
    agent._apis_declared_once = True
    agent._epistemic_once = True
    names = agent._action_tool_names()
    assert "read_file" in names
    assert names[0] == "read_file"
    assert "edit_file" in names
    assert "run_tests" in names


def test_tests_still_required_after_failures_even_without_test_goal() -> None:
    agent = Agent(model_runner=_DummyModel(), require_tools=True)
    agent._acted_once = True
    agent._task_wants_tests = False
    agent._ran_tests_ok = False
    agent._run_tests_failures = 1
    assert agent._tests_still_required() is True
    assert agent._needs_tool() is True


def test_sanitize_thought_dedupes_repeated_sentences() -> None:
    from mango_agent.agent import _sanitize_thought

    text = (
        "The bot is complete and the smoke run passed. "
        "The bot is complete and the smoke run passed. "
        "The bot is complete and the smoke run passed."
    )
    display, _ = _sanitize_thought(text, max_sentences=5, max_chars=500)
    assert display.count("bot is complete") == 1


def test_note_stall_stops_after_identical_answers(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_STALL_MODE", "hard")

    class _Engine:
        def __init__(self) -> None:
            self.feedback = ""

        def set_verification_feedback(self, text: str) -> None:
            self.feedback = text

    agent = Agent(model_runner=_DummyModel(), require_tools=True)
    engine = _Engine()
    same = "The bot is complete and the smoke run passed."
    assert agent._note_stall(same, engine) is False
    assert agent._note_stall(same, engine) is False
    assert agent._note_stall(same, engine) is False  # escalate at 2, not stop yet
    assert "same answer" in engine.feedback.lower() or "tool call" in engine.feedback.lower()
    assert agent._note_stall(same, engine) is False
    assert agent._note_stall(same, engine) is True
    agent._clear_stall()
    assert agent._note_stall(same, engine) is False


def test_human_part_strips_schema_meta() -> None:
    from mango_agent.agent import _human_part

    assert _human_part("Bot ready | next=string | verify=string") == "Bot ready"
    assert "next=" not in _human_part("string | next=string")
