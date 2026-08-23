"""Action-loop guard: block repeated identical reads/edits and force write_file."""

from __future__ import annotations

from pathlib import Path

from mango_agent.agent import Agent, _ACTION_LOOP_NUDGE
from mango_agent.prompt import feedback
from mango_runtime.types import CompletionResult
from mango_tools.types import ToolCall, ToolResult


class _DummyModel:
    def complete(self, *args, **kwargs):
        return CompletionResult(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)


class _Engine:
    def __init__(self) -> None:
        self.feedback = ""

    def set_verification_feedback(self, text: str) -> None:
        self.feedback = text


def _agent(tmp_path: Path) -> Agent:
    return Agent(
        model_runner=_DummyModel(),
        require_tools=True,
        verification_root=str(tmp_path),
        codeintel_root=str(tmp_path),
    )


def test_feedback_action_loop_sections_exist() -> None:
    assert "write_file" in feedback("action_loop", action="read_file x.py")
    assert "BLOCKED" in feedback("action_loop_blocked", action="read_file x.py")


def test_reread_without_mutation_is_blocked(tmp_path: Path) -> None:
    target = tmp_path / "wordstats.py"
    target.write_text("def main():\n    return 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._current_iteration = 1
    abs_path = str(target.resolve())
    agent._files_read.add(abs_path)
    agent._path_last_read_iter[abs_path] = 1
    call = ToolCall(
        name="read_file",
        arguments={"path": "wordstats.py"},
        raw="",
        start=0,
        end=0,
    )
    fp = agent._tool_call_fingerprint(call)
    agent._call_fp_counts[fp] = 1

    reason = agent._action_loop_block_reason(call)
    assert reason is not None
    assert "BLOCKED" in reason
    assert agent._action_loop_force_write is True
    assert agent._forced_tool_name() == "write_file"


def test_reread_allowed_after_successful_mutation(tmp_path: Path) -> None:
    target = tmp_path / "wordstats.py"
    target.write_text("x = 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._current_iteration = 3
    abs_path = str(target.resolve())
    agent._files_read.add(abs_path)
    agent._path_last_read_iter[abs_path] = 1
    agent._path_last_mutate_iter[abs_path] = 2
    call = ToolCall(
        name="read_file",
        arguments={"path": "wordstats.py"},
        raw="",
        start=0,
        end=0,
    )
    agent._call_fp_counts[agent._tool_call_fingerprint(call)] = 1
    assert agent._action_loop_block_reason(call) is None


def test_identical_failed_edit_is_blocked(tmp_path: Path) -> None:
    target = tmp_path / "wordstats.py"
    target.write_text("x = 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    abs_path = str(target.resolve())
    agent._files_read.add(abs_path)
    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "wordstats.py",
            "old_string": "x = 1",
            "new_string": "x = 2\nif __name__ == '__main__':\n    pass\n",
        },
        raw="",
        start=0,
        end=0,
    )
    fp = agent._tool_call_fingerprint(call)
    agent._call_fp_counts[fp] = 1
    agent._edit_fail_counts[abs_path + ":abc"] = 2

    reason = agent._action_loop_block_reason(call)
    assert reason is not None
    assert agent._action_loop_force_write is True


def test_thought_inspect_loop_redirects(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    engine = _Engine()
    calls = [
        ToolCall(name="read_file", arguments={"path": "wordstats.py"}, raw="", start=0, end=0)
    ]
    thought = "The file is missing if __name__ == '__main__'. I need to read it then edit."
    for _ in range(_ACTION_LOOP_NUDGE):
        agent._note_thought_action_loop(engine, thought, calls)
    assert agent._action_loop_force_write is True
    assert engine.feedback
    assert agent._forced_tool_name() == "write_file"


def test_note_results_nudges_on_repeat_reads(tmp_path: Path) -> None:
    target = tmp_path / "wordstats.py"
    target.write_text("x = 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    engine = _Engine()
    call = ToolCall(
        name="read_file",
        arguments={"path": "wordstats.py"},
        raw="",
        start=0,
        end=0,
    )
    result = ToolResult(
        success=True,
        tool_name="read_file",
        output={"path": "wordstats.py", "absolute_path": str(target.resolve())},
        call=call,
    )
    agent._current_iteration = 1
    for _ in range(_ACTION_LOOP_NUDGE):
        agent._note_action_loop_results(engine, [call], [result])
        agent._current_iteration += 1
    assert agent._call_fp_counts[agent._tool_call_fingerprint(call)] >= _ACTION_LOOP_NUDGE
    assert agent._action_loop_force_write is True
    assert engine.feedback
