from __future__ import annotations

from pathlib import Path

import pytest

from mango_agent import Agent
from mango_agent.agent import _GOAL_WANTS_TESTS_WRITTEN, _PYTEST_NO_TESTS_EXIT
from mango_context import ContextEngine
from mango_tools import create_default_registry
from mango_tools.types import ToolCall, ToolResult
from test_agent_loop import FakeModelRunner


def _agent(tmp_path: Path, **kwargs) -> Agent:
    return Agent(
        FakeModelRunner(["done"]),
        max_iterations=3,
        verification_root=tmp_path,
        require_tools=True,
        tool_registry=create_default_registry(),
        **kwargs,
    )


def test_run_tests_blocked_when_no_test_files_exist(tmp_path: Path) -> None:
    (tmp_path / "inventory.py").write_text("def total(): return 0\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent.run("Fix inventory.py so total() returns the sum.")
    call = ToolCall(name="run_tests", arguments={}, raw="", start=0, end=0)
    reason = agent._grounding_block_reason(call)
    assert reason is not None
    assert "BLOCKED" in reason
    assert "write_file" in reason.lower()


def test_exit_five_feedback_says_write_tests_not_read_impl(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    engine = ContextEngine(goal="fix inventory")
    empty_test = tmp_path / "test_inventory.py"
    empty_test.write_text("# no tests here\n", encoding="utf-8")
    result = ToolResult(
        success=True,
        tool_name="run_tests",
        output={
            "ok": False,
            "exit_code": _PYTEST_NO_TESTS_EXIT,
            "targets": [str(empty_test.resolve())],
            "stdout": "targets: test_inventory.py\nno tests ran in 0.02s\n",
            "stderr": "",
        },
        call=ToolCall(name="run_tests", arguments={}, raw="", start=0, end=0),
    )
    agent._handle_run_tests_results([result], engine)
    feedback = engine.state.verification_feedback or ""
    assert "write_file" in feedback.lower() or "no test" in feedback.lower()
    assert "read_file" not in feedback.lower() or "write_file" in feedback.lower()
    assert agent._run_tests_failures == 0


def test_cleanup_deletes_agent_created_tests_by_default(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    agent._keep_agent_tests = False
    test_path = tmp_path / "test_inventory.py"
    test_path.write_text("def test_x(): pass\n", encoding="utf-8")
    agent._agent_created_test_paths = [str(test_path.resolve())]
    removed = agent._cleanup_agent_tests()
    assert removed == [str(test_path.resolve())]
    assert not test_path.is_file()


def test_cleanup_keeps_tests_when_goal_asked_for_tests(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    agent._keep_agent_tests = True
    test_path = tmp_path / "test_inventory.py"
    test_path.write_text("def test_x(): pass\n", encoding="utf-8")
    agent._agent_created_test_paths = [str(test_path.resolve())]
    removed = agent._cleanup_agent_tests()
    assert removed == []
    assert test_path.is_file()


@pytest.mark.parametrize(
    "goal",
    [
        "Schreibe Tests für inventory.py",
        "write tests for inventory.py",
        "Erstelle test_foo.py",
    ],
)
def test_goal_wants_tests_written_regex(goal: str) -> None:
    assert _GOAL_WANTS_TESTS_WRITTEN.search(goal)


def test_test_only_mutation_skips_experiment_revert(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    engine = ContextEngine(goal="fix inventory")
    test_path = tmp_path / "test_inventory.py"
    test_path.write_text("def test_x(): assert False\n", encoding="utf-8")
    snapshots = {str(test_path.resolve()): ""}
    tool_results = [
        ToolResult(
            success=True,
            tool_name="write_file",
            output={"path": str(test_path), "absolute_path": str(test_path.resolve())},
            call=ToolCall(
                name="write_file",
                arguments={"path": str(test_path), "content": "def test_x(): assert False\n"},
                raw="",
                start=0,
                end=0,
            ),
        ),
        ToolResult(
            success=True,
            tool_name="run_tests",
            output={"ok": False, "exit_code": 1, "targets": [str(test_path.resolve())]},
            call=ToolCall(name="run_tests", arguments={}, raw="", start=0, end=0),
        ),
    ]
    reverted = agent._conclude_experiment(
        engine, snapshots, tool_results, syntax_bad=False, iteration=1
    )
    assert reverted is False
    assert test_path.is_file()


def test_experiment_revert_deletes_newly_created_file(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    new_file = tmp_path / "scratch.py"
    new_file.write_text("x = 1\n", encoding="utf-8")
    snapshots = {str(new_file.resolve()): ""}
    restored = agent._restore_experiment_files(snapshots)
    assert str(new_file.resolve()) in restored
    assert not new_file.is_file()


def test_experiment_revert_restores_edited_impl(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    engine = ContextEngine(goal="fix inventory")
    impl = tmp_path / "inventory.py"
    impl.write_text("def total(): return 1\n", encoding="utf-8")
    snapshots = {str(impl.resolve()): "def total(): return 0\n"}
    tool_results = [
        ToolResult(
            success=True,
            tool_name="edit_file",
            output={"path": str(impl), "absolute_path": str(impl.resolve())},
            call=ToolCall(
                name="edit_file",
                arguments={"path": str(impl), "old_string": "return 0", "new_string": "return 1"},
                raw="",
                start=0,
                end=0,
            ),
        ),
        ToolResult(
            success=True,
            tool_name="run_tests",
            output={"ok": False, "exit_code": 1, "targets": []},
            call=ToolCall(name="run_tests", arguments={}, raw="", start=0, end=0),
        ),
    ]
    restored = agent._restore_experiment_files(snapshots)
    assert str(impl.resolve()) in restored
    assert impl.read_text(encoding="utf-8") == "def total(): return 0\n"


def test_read_missing_file_redirects_to_write(tmp_path: Path) -> None:
    """read_file on a non-existent path must block and force write_file (no File-not-found loop)."""
    agent = _agent(tmp_path)
    agent.run("Write revenue_report.txt with desk=1750.")
    call = ToolCall(
        name="read_file",
        arguments={"path": "revenue_report.txt"},
        raw="",
        start=0,
        end=0,
    )
    reason = agent._grounding_block_reason(call)
    assert reason is not None
    assert "does not exist" in reason.lower()
    assert "write_file" in reason.lower()
    assert agent._prefer_write_file is True
    assert agent._forced_tool_name() == "write_file"


def test_read_missing_during_research_redirects_to_unread_input(tmp_path: Path) -> None:
    """While inputs remain unread, missing-output read is steered to the next input."""
    (tmp_path / "sales_jan.csv").write_text("month,item,amount\nJan,desk,3\n", encoding="utf-8")
    (tmp_path / "prices.txt").write_text("desk=250\n", encoding="utf-8")
    agent = _agent(tmp_path)
    agent.run(
        "Read sales_jan.csv and prices.txt. Write revenue_report.txt with desk=750."
    )
    call = ToolCall(
        name="read_file",
        arguments={"path": "revenue_report.txt"},
        raw="",
        start=0,
        end=0,
    )
    reason = agent._grounding_block_reason(call)
    assert reason is not None
    assert "sales_jan.csv" in reason or "prices.txt" in reason
    assert agent._forced_tool_name() == "read_file"


def test_edit_missing_file_redirects_to_write(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    agent.run("Create helper.py with a greet function.")
    call = ToolCall(
        name="edit_file",
        arguments={"path": "helper.py", "old_string": "x", "new_string": "y"},
        raw="",
        start=0,
        end=0,
    )
    reason = agent._grounding_block_reason(call)
    assert reason is not None
    assert "write_file" in reason.lower()
    assert agent._prefer_write_file is True


def test_cli_goal_caps_write_tokens_and_switches_to_edit_after_gaps(tmp_path: Path) -> None:
    """Inventory-style CLI must not dump/rewrite forever after a partial write."""
    from mango_context import ContextEngine

    agent = _agent(tmp_path)
    # Don't call full run — just arm CLI goal state like Agent.run does.
    agent._cli_goal = True
    agent._write_tool_max_tokens = 1024
    agent._task = (
        "schreib ein python projekt, das über die konsole läuft. "
        "inventory: add, update, remove, beschreibungen"
    )
    agent._verification_root = tmp_path
    agent._require_tools = True
    (tmp_path / "inventory.py").write_text(
        "import argparse\n\ndef load_inventory():\n    return {}\n",
        encoding="utf-8",
    )
    engine = ContextEngine(goal=agent._task)
    agent._refresh_impl_completeness(engine)
    assert agent._impl_gaps
    agent._incomplete_impl_writes = 1
    agent._prefer_edit_gaps = True
    agent._prefer_write_file = False
    agent._prefer_read_file = True
    assert agent._forced_tool_name() == "read_file"
    agent._prefer_read_file = False
    assert agent._forced_tool_name() == "edit_file"
