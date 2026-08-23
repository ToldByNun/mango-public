"""End-to-end: wordstats-style goal must stop after green tests, not thrash edits."""

from __future__ import annotations

import json
from pathlib import Path

from mango_agent import Agent, StopReason
from mango_agent.agent import Agent as AgentClass
from mango_runtime.types import CompletionResult
from mango_tools import create_default_registry
from mango_tools.types import ToolCall
from test_agent_loop import FakeModelRunner

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

IMPL = 'import argparse\nfrom collections import Counter\n\ndef count_words(text):\n    words = []\n    for token in text.lower().split():\n        word = token.strip(".,!?;:\'\\"()[]{}")\n        if word:\n            words.append(word)\n    return Counter(words)\n\ndef main(argv=None):\n    parser = argparse.ArgumentParser(description="Word frequency statistics")\n    parser.add_argument("path", help="Path to the text file")\n    args = parser.parse_args(argv)\n    try:\n        with open(args.path, encoding="utf-8") as handle:\n            text = handle.read()\n    except FileNotFoundError:\n        print(f"Error: file not found: {args.path}")\n        return 1\n    for word, count in count_words(text).most_common(10):\n        print(f"{word}: {count}")\n    return 0\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'

IMPL_NO_MAIN = 'import argparse\nfrom collections import Counter\n\ndef count_words(text):\n    words = []\n    for token in text.lower().split():\n        word = token.strip(".,!?;:\'\\"()[]{}")\n        if word:\n            words.append(word)\n    return Counter(words)\n\ndef main(argv=None):\n    parser = argparse.ArgumentParser(description="Word frequency statistics")\n    parser.add_argument("path", help="Path to the text file")\n    args = parser.parse_args(argv)\n    try:\n        with open(args.path, encoding="utf-8") as handle:\n            text = handle.read()\n    except FileNotFoundError:\n        print(f"Error: file not found: {args.path}")\n        return 1\n    for word, count in count_words(text).most_common(10):\n        print(f"{word}: {count}")\n    return 0\n\n'

TESTS = 'from wordstats import count_words, main\n\ndef test_count_words_normal():\n    result = count_words("Hello hello world HELLO")\n    assert result["hello"] == 3\n    assert result["world"] == 1\n\ndef test_count_words_empty():\n    assert count_words("") == {}\n\ndef test_file_not_found():\n    assert main(["___missing_wordstats_file___.txt"]) == 1\n'

BROKEN_EDIT = {
    "path": "wordstats.py",
    "old_string": IMPL,
    "new_string": IMPL.replace(
        "if __name__ == \"__main__\":\n    raise SystemExit(main())\n",
        "if __name__ == '__main__':\n    main()\n\ndef main(argv=None):\n    pass\n",
    ),
}

SHRINK_WRITE = {
    "path": "wordstats.py",
    "content": "def main():\n    pass\n",
}


class _DummyModel:
    def complete(self, *args, **kwargs):
        return CompletionResult(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)


def _make_agent(tmp_path: Path, runner=None) -> Agent:
    return Agent(
        runner or FakeModelRunner(["Done."]),
        max_iterations=10,
        require_tools=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        task_wants_tests=True,
    )


def test_wordstats_complete_stops_without_thrash(tmp_path: Path) -> None:
    """a) Complete wordstats with __main__ + tests -> COMPLETED, no thrash edit."""
    write_impl = f'<tool_call=write_file : {json.dumps({"path": "wordstats.py", "content": IMPL})}>'
    write_tests = f'<tool_call=write_file : {json.dumps({"path": "test_wordstats.py", "content": TESTS})}>'
    run_tests = "<tool_call=run_tests : {}>"
    thrash = f"<tool_call=edit_file : {json.dumps(BROKEN_EDIT)}>"
    runner = FakeModelRunner(
        [
            f"Creating wordstats.py.\n{write_impl}",
            f"Adding unit tests.\n{write_tests}",
            f"Running tests.\n{run_tests}",
            f"Hypothesis: entry point missing.\n{thrash}",
            "Done.",
            "Done.",
        ]
    )
    agent = _make_agent(tmp_path, runner)
    result = agent.run(WORDSTATS_GOAL)
    assert result.error is None, result.error
    assert result.stop_reason == StopReason.COMPLETED
    assert agent._goal_met is True
    assert agent._ran_tests_ok is True
    source = (tmp_path / "wordstats.py").read_text(encoding="utf-8")
    assert "def main" in source
    assert "if __name__" in source
    assert any(thrash in leftover for leftover in runner._outputs)
    assert "def main(argv=None):\n    pass" not in source


def test_wordstats_missing_main_autoheals_or_completes(tmp_path: Path) -> None:
    """b) Incomplete without __main__ but main()+tests pass -> heal or no shrink thrash."""
    write_impl = f'<tool_call=write_file : {json.dumps({"path": "wordstats.py", "content": IMPL_NO_MAIN})}>'
    write_tests = f'<tool_call=write_file : {json.dumps({"path": "test_wordstats.py", "content": TESTS})}>'
    run_tests = "<tool_call=run_tests : {}>"
    shrink = f'<tool_call=write_file : {json.dumps(SHRINK_WRITE)}>'
    runner = FakeModelRunner(
        [
            f"Creating wordstats.py.\n{write_impl}",
            f"Adding unit tests.\n{write_tests}",
            f"Running tests.\n{run_tests}",
            f"Rewriting file.\n{shrink}",
            "Done.",
            "Done.",
            "Done.",
        ]
    )
    agent = _make_agent(tmp_path, runner)
    result = agent.run(WORDSTATS_GOAL)
    assert result.error is None, result.error
    assert result.stop_reason == StopReason.COMPLETED
    source = (tmp_path / "wordstats.py").read_text(encoding="utf-8")
    assert "def main" in source
    assert "if __name__" in source
    assert "def main():\n    pass" not in source
    assert agent._ran_tests_ok is True or agent._goal_met is True


def test_arm_redirect_after_pytest_green_does_not_force_write(tmp_path: Path) -> None:
    """c) After _pytest_green, _arm_action_loop_redirect does NOT set force write."""
    agent = AgentClass(
        model_runner=_DummyModel(),
        require_tools=True,
        verification_root=str(tmp_path),
        codeintel_root=str(tmp_path),
        task_wants_tests=True,
    )
    agent._pytest_green = True
    agent._arm_action_loop_redirect("read_file wordstats.py")
    assert agent._action_loop_force_write is False
    assert agent._prefer_write_file is False


def test_blocked_reread_after_pytest_green_does_not_arm_write(tmp_path: Path) -> None:
    """d) After _pytest_green, blocked re-read does NOT arm write redirect."""
    (tmp_path / "wordstats.py").write_text(IMPL, encoding="utf-8")
    agent = AgentClass(
        model_runner=_DummyModel(),
        require_tools=True,
        verification_root=str(tmp_path),
        codeintel_root=str(tmp_path),
        task_wants_tests=True,
    )
    agent._pytest_green = True
    agent._ran_tests_ok = True
    abs_path = str((tmp_path / "wordstats.py").resolve())
    agent._files_read.add(abs_path)
    agent._path_last_read_iter[abs_path] = 2
    agent._path_last_mutate_iter[abs_path] = 1
    agent._current_iteration = 3
    call = ToolCall(name="read_file", arguments={"path": "wordstats.py"}, raw="", start=0, end=0)
    fp = agent._tool_call_fingerprint(call)
    agent._call_fp_counts[fp] = 1
    reason = agent._action_loop_block_reason(call)
    assert reason is not None
    assert agent._action_loop_force_write is False
    assert agent._forced_tool_name() != "write_file"


def test_greeter_stops_after_green_tests(tmp_path: Path) -> None:
    impl = (
        "import argparse\n\n"
        "def greet(name):\n    return f'Hello {name}'\n\n"
        "def main(argv=None):\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('name')\n"
        "    args = p.parse_args(argv)\n"
        "    print(greet(args.name))\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )
    tests = (
        "from greeter import greet\n\n"
        "def test_greet():\n"
        "    assert greet('Ada') == 'Hello Ada'\n"
    )
    write_impl = f'<tool_call=write_file : {json.dumps({"path": "greeter.py", "content": impl})}>'
    write_tests = f'<tool_call=write_file : {json.dumps({"path": "test_greeter.py", "content": tests})}>'
    run_tests = "<tool_call=run_tests : {}>"
    thrash = (
        f'<tool_call=edit_file : {json.dumps({"path": "greeter.py", "old_string": "return 0", "new_string": "return 1"})}>'
    )
    runner = FakeModelRunner([write_impl, write_tests, run_tests, thrash, "Done."])
    agent = _make_agent(tmp_path, runner)
    result = agent.run(
        "Create greeter.py: a small CLI that prints Hello <name>. "
        "Include argparse, an entry point, and unit tests."
    )
    assert result.stop_reason == StopReason.COMPLETED
    assert agent._ran_tests_ok is True
    assert any(thrash in leftover for leftover in runner._outputs)
    assert "return 1" not in (tmp_path / "greeter.py").read_text(encoding="utf-8")


def test_todo_cli_stops_after_green_tests(tmp_path: Path) -> None:
    impl = (
        "import argparse\n\n"
        "_ITEMS: list[str] = []\n\n"
        "def add_item(text: str) -> None:\n"
        "    _ITEMS.append(text)\n\n"
        "def list_items() -> list[str]:\n"
        "    return list(_ITEMS)\n\n"
        "def main(argv=None):\n"
        "    p = argparse.ArgumentParser()\n"
        "    sub = p.add_subparsers(dest='cmd', required=True)\n"
        "    add_p = sub.add_parser('add')\n"
        "    add_p.add_argument('text')\n"
        "    sub.add_parser('list')\n"
        "    args = p.parse_args(argv)\n"
        "    if args.cmd == 'add':\n"
        "        add_item(args.text)\n"
        "        return 0\n"
        "    print('\\n'.join(list_items()))\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )
    tests = (
        "from todo import add_item, list_items, main\n\n"
        "def test_add_list():\n"
        "    add_item('x')\n"
        "    assert list_items() == ['x']\n\n"
        "def test_main_add():\n"
        "    assert main(['add', 'a']) == 0\n"
    )
    write_impl = f'<tool_call=write_file : {json.dumps({"path": "todo.py", "content": impl})}>'
    write_tests = f'<tool_call=write_file : {json.dumps({"path": "test_todo.py", "content": tests})}>'
    run_tests = "<tool_call=run_tests : {}>"
    thrash = (
        f'<tool_call=edit_file : {json.dumps({"path": "todo.py", "old_string": "return 0", "new_string": "return 99"})}>'
    )
    runner = FakeModelRunner([write_impl, write_tests, run_tests, thrash, "Done."])
    agent = _make_agent(tmp_path, runner)
    result = agent.run(
        "Write a Python CLI todo.py with add/list commands using argparse, "
        "an if __name__ entry point, and unit tests."
    )
    assert result.stop_reason == StopReason.COMPLETED
    assert agent._ran_tests_ok is True
    assert any(thrash in leftover for leftover in runner._outputs)
