"""A0b: grammar completeness vs legacy strip + preferred-tool feedback."""

from __future__ import annotations

from mango_agent.agent import Agent
from mango_agent.flags import RECOVERY_CORE_TOOLS
from mango_agent.metrics import missing_core_tools
from mango_runtime.types import CompletionResult
from mango_tools import create_default_registry


class _DummyModel:
    def complete(self, *args, **kwargs):
        return CompletionResult(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)


def _agent(**kwargs) -> Agent:
    return Agent(
        model_runner=_DummyModel(),
        require_tools=True,
        use_tool_grammar=True,
        tool_registry=create_default_registry(),
        **kwargs,
    )


def test_complete_mode_keeps_read_file_after_pytest_fail(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_TOOL_FILTER_MODE", "complete")
    agent = _agent()
    agent._acted_once = True
    agent._task_wants_tests = True
    agent._ran_tests_ok = False
    agent._run_tests_failures = 2
    agent._last_verification_ok = False
    agent._apis_declared_once = True
    agent._epistemic_once = True
    names = agent._action_tool_names()
    assert "read_file" in names
    assert "edit_file" in names
    assert "write_file" in names
    assert "run_tests" in names
    available = set(agent._enabled_registry_names())
    assert missing_core_tools(names, available=available) == []


def test_complete_mode_keeps_read_and_write_after_edit_fail(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_TOOL_FILTER_MODE", "complete")
    agent = _agent()
    agent._acted_once = True
    agent._prefer_read_file = True
    agent._prefer_write_file = True
    agent._task_wants_tests = True
    agent._ran_tests_ok = False
    agent._run_tests_failures = 1
    agent._apis_declared_once = True
    agent._epistemic_once = True
    names = agent._action_tool_names()
    assert "read_file" in names
    assert "write_file" in names
    assert agent._last_preferred_tools[0] in {"read_file", "write_file", "edit_file"}


def test_complete_mode_design_review_prefers_read_but_keeps_edit(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_TOOL_FILTER_MODE", "complete")
    agent = _agent()
    agent._acted_once = True
    agent._review_needed = True
    agent._review_done = False
    agent._apis_declared_once = True
    agent._epistemic_once = True
    # Force design-review path.
    agent._design_review_still_required = lambda: True  # type: ignore[method-assign]
    names = agent._action_tool_names()
    assert "read_file" in names
    assert "edit_file" in names
    assert agent._last_preferred_tools[0] == "read_file"


def test_complete_mode_declare_phase_prefers_declare_keeps_read(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_TOOL_FILTER_MODE", "complete")
    agent = _agent(plan_apis_first=True)
    agent._apis_declared_once = False
    agent._epistemic_once = False
    agent._plan_gate_phase = lambda: "declare"  # type: ignore[method-assign]
    names = agent._action_tool_names()
    assert "declare_apis" in names
    assert "read_file" in names
    assert "search_code" in names
    assert agent._last_preferred_tools[0] == "declare_apis"


def test_legacy_mode_still_strips_read_after_verification_fail(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_TOOL_FILTER_MODE", "legacy")
    agent = _agent()
    agent._acted_once = True
    agent._last_verification_ok = False
    agent._apis_declared_once = True
    agent._epistemic_once = True
    names = agent._action_tool_names_legacy()
    assert "read_file" not in names
    assert "run_tests" in names or "edit_file" in names or "write_file" in names


def test_legacy_design_review_strips_to_read_only(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_TOOL_FILTER_MODE", "legacy")
    agent = _agent()
    agent._acted_once = True
    agent._design_review_still_required = lambda: True  # type: ignore[method-assign]
    names = agent._action_tool_names_legacy()
    assert names == ["read_file"]


def test_preferred_feedback_injected(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_TOOL_FILTER_MODE", "complete")

    class _Engine:
        def __init__(self) -> None:
            self.state = type("S", (), {"verification_feedback": "tests failed"})()

        def set_verification_feedback(self, text: str) -> None:
            self.state.verification_feedback = text

    agent = _agent()
    agent._last_preferred_tools = ["read_file", "edit_file"]
    engine = _Engine()
    agent._apply_preferred_tool_feedback(engine)
    text = engine.state.verification_feedback
    assert "tests failed" in text
    assert "Preferred next tools: read_file, edit_file" in text


def test_recovery_core_constant_covers_read_edit_write() -> None:
    assert {"read_file", "edit_file", "write_file", "run_tests"} <= RECOVERY_CORE_TOOLS
