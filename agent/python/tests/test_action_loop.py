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


def test_codebase_lookup_repeat_blocked_for_swebench(tmp_path: Path) -> None:
    """SWE-bench disables write_file — repeat lookup must steer to edit/read."""
    agent = _agent(tmp_path)
    agent._disabled_tools = frozenset({"write_file", "run_terminal_command"})
    agent._located_once = True
    call = ToolCall(
        name="codebase_lookup",
        arguments={"query": "Where is separability_matrix defined?"},
        raw="",
        start=0,
        end=0,
    )
    fp = agent._tool_call_fingerprint(call)
    agent._call_fp_counts[fp] = 1
    reason = agent._action_loop_block_reason(call)
    assert reason is not None
    assert "BLOCKED" in reason
    assert agent._action_loop_force_edit is True
    assert agent._action_loop_force_write is False
    assert agent._prefer_read_file is False
    assert agent._inspected_once is True


def test_patch_mode_missing_file_redirects_to_search(tmp_path: Path) -> None:
    """Invented paths must not demand write_file when write_file is disabled."""
    real = tmp_path / "xarray" / "core" / "dataarray.py"
    real.parent.mkdir(parents=True)
    real.write_text("class DataArray:\n    pass\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._disabled_tools = frozenset({"write_file", "run_terminal_command"})
    agent._task = "Fix DataArray indexing"
    call = ToolCall(
        name="read_file",
        arguments={"path": "xarray/core/missing_typo.py"},
        raw="",
        start=0,
        end=0,
    )
    reason = agent._grounding_block_reason(call)
    assert reason is not None
    assert "write_file" not in reason.lower() or "do not call write_file" in reason.lower()
    assert "search_code" in reason.lower() or "codebase_lookup" in reason.lower()
    assert agent._prefer_write_file is False
    assert agent._action_loop_force_write is False


def test_patch_mode_missing_file_hints_real_basename(tmp_path: Path) -> None:
    real = tmp_path / "pkg" / "utils.py"
    real.parent.mkdir(parents=True)
    real.write_text("def helper():\n    return 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._disabled_tools = frozenset({"write_file"})
    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "wrong/utils.py",
            "old_string": "return 1",
            "new_string": "return 2",
        },
        raw="",
        start=0,
        end=0,
    )
    reason = agent._grounding_block_reason(call)
    assert reason is not None
    assert "utils.py" in reason
    assert agent._prefer_read_file is True
    assert agent._forced_tool_name() == "read_file"


def test_patch_mode_reread_blocks_with_snippet_not_write(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._disabled_tools = frozenset({"write_file", "run_terminal_command"})
    abs_path = str(target.resolve())
    agent._files_read.add(abs_path)
    agent._path_last_read_iter[abs_path] = 1
    agent._current_iteration = 2
    call = ToolCall(
        name="read_file",
        arguments={"path": "mod.py"},
        raw="",
        start=0,
        end=0,
    )
    agent._call_fp_counts[agent._tool_call_fingerprint(call)] = 1
    reason = agent._action_loop_block_reason(call)
    assert reason is not None
    assert "write_file" not in reason.lower() or "do not call write_file" in reason.lower()
    assert "edit_file" in reason.lower()
    assert agent._action_loop_force_edit is True
    assert agent._action_loop_force_write is False
    assert agent._forced_tool_name() == "edit_file"


def test_patch_mode_failed_edit_does_not_force_write(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._disabled_tools = frozenset({"write_file", "run_terminal_command"})
    engine = _Engine()
    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "mod.py",
            "old_string": "this is not in the file",
            "new_string": "return a + b",
        },
        raw="",
        start=0,
        end=0,
    )
    fail = ToolResult(
        success=False,
        tool_name="edit_file",
        error="old_string not found in file",
        call=call,
    )
    agent._feedback_failed_tools(engine, [fail])
    assert agent._prefer_write_file is False
    assert "write_file" not in engine.feedback.lower() or "do not" in engine.feedback.lower()
    assert "edit_file" in engine.feedback.lower() or "read_file" in engine.feedback.lower()
    # Second identical fail → snippet + force edit
    agent._feedback_failed_tools(engine, [fail])
    assert agent._prefer_write_file is False
    assert agent._action_loop_force_edit is True or agent._prefer_read_file is True


def test_patch_already_applied_requires_new_string_present(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._disabled_tools = frozenset({"write_file"})
    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "mod.py",
            "old_string": "never matched",
            "new_string": "also never matched",
        },
        raw="",
        start=0,
        end=0,
    )
    agent._call_fp_counts[agent._tool_call_fingerprint(call)] = 1
    reason = agent._action_loop_block_reason(call)
    assert reason is not None
    assert "already on disk" not in reason.lower()
    assert agent._goal_met is False


def test_action_loop_force_edit_grammar_not_read_only(tmp_path: Path) -> None:
    """SWE-bench: action-loop edit redirect must not sole-lock grammar to read_file."""
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir(parents=True)
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent._disabled_tools = frozenset({"write_file", "run_terminal_command"})
    agent._located_once = True
    agent._inspected_once = True
    agent._prefer_read_file = True
    agent._action_loop_force_edit = True
    agent._prefer_edit_gaps = True
    names = agent._apply_grammar_filters(agent._enabled_registry_names())
    assert names == ["edit_file"]


def test_note_results_increments_fingerprint(tmp_path: Path) -> None:
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
