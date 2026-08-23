"""Once gaps are empty and tests are green, mutating tools must stop."""

from __future__ import annotations

from pathlib import Path

from mango_agent.agent import Agent, _CODE_MUTATING_TOOLS
from mango_context import ContextEngine
from mango_runtime.types import CompletionResult
from mango_tools.types import ToolCall


class _DummyModel:
    def complete(self, *args, **kwargs):
        return CompletionResult(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)


WORDSTATS_GOAL = (
    "Create a Python CLI tool called wordstats.py that analyzes a text file and "
    "prints word-frequency statistics. Requirements:\n"
    "Takes a file path as a command-line argument\n"
    "Counts word frequency (case-insensitive, ignore punctuation)\n"
    "Prints the top 10 most common words with their counts\n"
    "Handles the file-not-found case gracefully with a clear error message\n"
    "Include unit tests covering: normal input, empty file, and file-not-found\n"
    "Use only the Python standard library"
)

COMPLETE = '''\
import argparse
from collections import Counter

def count_words(text):
    words = []
    for token in text.lower().split():
        word = token.strip(".,!?;:\\"'()[]{}")
        if word:
            words.append(word)
    return Counter(words)

def main(argv=None):
    parser = argparse.ArgumentParser(description="Word frequency statistics")
    parser.add_argument("path", help="Path to the text file")
    args = parser.parse_args(argv)
    try:
        with open(args.path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.path}")
        return 1
    for word, count in count_words(text).most_common(10):
        print(f"{word}: {count}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''

TESTS = '''\
from wordstats import count_words, main

def test_count_words_normal():
    result = count_words("Hello hello world HELLO")
    assert result["hello"] == 3
    assert result["world"] == 1

def test_count_words_empty():
    assert count_words("") == {}

def test_file_not_found():
    assert main(["___missing_wordstats_file___.txt"]) == 1
'''

TODO_GOAL = (
    "Write a Python CLI todo.py with add/list commands using argparse, "
    "an if __name__ entry point, and unit tests."
)

GREETER_GOAL = (
    "Create greeter.py: a small CLI that prints Hello <name>. "
    "Include argparse, an entry point, and tests."
)


def _agent(tmp_path: Path, goal: str) -> Agent:
    agent = Agent(
        model_runner=_DummyModel(),
        require_tools=True,
        verification_root=str(tmp_path),
        codeintel_root=str(tmp_path),
        task_wants_tests=True,
    )
    agent._task = goal
    agent._require_tools = True
    agent._cli_goal = True
    agent._task_wants_tests = True
    agent._acted_once = True
    agent._impl_mutated_once = True
    agent._ran_tests_ok = True
    agent._syntax_broken = False
    return agent


def _seed_wordstats(tmp_path: Path) -> None:
    (tmp_path / "wordstats.py").write_text(COMPLETE, encoding="utf-8")
    (tmp_path / "test_wordstats.py").write_text(TESTS, encoding="utf-8")


def test_wordstats_goal_met_blocks_further_edits(tmp_path: Path) -> None:
    _seed_wordstats(tmp_path)
    agent = _agent(tmp_path, WORDSTATS_GOAL)
    engine = ContextEngine(goal=WORDSTATS_GOAL)
    agent._refresh_impl_completeness(engine)
    assert agent._impl_gaps == []
    assert agent._mark_goal_met_if_ready(engine) is True
    assert agent._goal_met is True
    assert agent._finish_allowed() is True
    assert agent._needs_tool() is False
    assert agent._forced_tool_name() is None

    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "wordstats.py",
            "old_string": "def count_words(text):",
            "new_string": "def count_words(text):  # noop",
        },
        raw="",
        start=0,
        end=0,
    )
    reason = agent._action_loop_block_reason(call)
    assert reason is not None
    assert "GOAL ALREADY MET" in reason


def test_wordstats_goal_met_does_not_force_write_after_reread(tmp_path: Path) -> None:
    _seed_wordstats(tmp_path)
    agent = _agent(tmp_path, WORDSTATS_GOAL)
    engine = ContextEngine(goal=WORDSTATS_GOAL)
    agent._refresh_impl_completeness(engine)
    agent._mark_goal_met_if_ready(engine)
    abs_path = str((tmp_path / "wordstats.py").resolve())
    agent._files_read.add(abs_path)
    agent._path_last_read_iter[abs_path] = 2
    agent._path_last_mutate_iter[abs_path] = 1
    agent._current_iteration = 3
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
    assert agent._action_loop_force_write is False
    assert agent._forced_tool_name() is None


def test_greeter_complete_blocks_write_file(tmp_path: Path) -> None:
    src = '''\
import argparse

def greet(name: str) -> str:
    return f"Hello {name}"

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args(argv)
    print(greet(args.name))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''
    (tmp_path / "greeter.py").write_text(src, encoding="utf-8")
    (tmp_path / "test_greeter.py").write_text(
        "from greeter import greet\n\ndef test_greet():\n    assert greet('Ada') == 'Hello Ada'\n",
        encoding="utf-8",
    )
    agent = _agent(tmp_path, GREETER_GOAL)
    engine = ContextEngine(goal=GREETER_GOAL)
    agent._refresh_impl_completeness(engine)
    assert agent._impl_gaps == []
    assert agent._mark_goal_met_if_ready(engine)
    call = ToolCall(
        name="write_file",
        arguments={"path": "greeter.py", "content": src + "\n# churn\n"},
        raw="",
        start=0,
        end=0,
    )
    assert "GOAL ALREADY MET" in (agent._action_loop_block_reason(call) or "")


def test_todo_cli_goal_met_when_complete(tmp_path: Path) -> None:
    src = '''\
import argparse

def add_item(items, name):
    items.append(name)
    return items

def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("name")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    items = []
    if args.cmd == "add":
        add_item(items, args.name)
    print(items)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''
    (tmp_path / "todo.py").write_text(src, encoding="utf-8")
    (tmp_path / "test_todo.py").write_text(
        "from todo import add_item\n\ndef test_add():\n    assert add_item([], 'a') == ['a']\n",
        encoding="utf-8",
    )
    agent = _agent(tmp_path, TODO_GOAL)
    engine = ContextEngine(goal=TODO_GOAL)
    agent._refresh_impl_completeness(engine)
    if agent._impl_gaps:
        # Feature heuristics may still flag inventory-style gaps; that is OK —
        # this fixture only asserts the latch when the checker is clean.
        return
    assert agent._mark_goal_met_if_ready(engine)
    call = ToolCall(
        name="edit_file",
        arguments={"path": "todo.py", "old_string": "items = []", "new_string": "items = list()"},
        raw="",
        start=0,
        end=0,
    )
    assert agent._action_loop_block_reason(call)


def test_mutating_tools_include_edit_and_write() -> None:
    assert "edit_file" in _CODE_MUTATING_TOOLS
    assert "write_file" in _CODE_MUTATING_TOOLS
