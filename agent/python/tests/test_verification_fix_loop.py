from __future__ import annotations

import json
import sys
from pathlib import Path

from mango_agent import Agent, StopReason
from test_agent_loop import FakeModelRunner


def _write_verify_project(tmp_path: Path) -> Path:
    target = tmp_path / "y.py"
    (tmp_path / "test_y.py").write_text(
        "from y import Y\n\n\ndef test_Y():\n    assert Y(1) == 2\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (tmp_path / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )
    return target


def test_verification_fix_loop_recovers_from_forced_bug(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    buggy = "def Y(x):\n    return x - 1\n"
    fixed = "def Y(x):\n    return x + 1\n"
    write_buggy = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": buggy})}>'
    )
    write_fixed = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": fixed})}>'
    )
    runner = FakeModelRunner(
        [
            write_buggy,
            write_fixed,
            "Implemented function Y. Verification passed.",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=6,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Implementiere Funktion Y in y.py so that Y(x) returns x + 1.")

    assert result.stop_reason == StopReason.COMPLETED
    assert target.read_text(encoding="utf-8") == fixed
    assert result.verification_attempts == 1
    assert agent.failed_verifications == 1
    assert len(runner.prompts) == 2

    second_prompt = runner.prompts[1]
    assert "## Verification" in second_prompt
    assert "failed" in second_prompt.lower()
    assert "test_Y" in second_prompt or "test_y.py" in second_prompt
    assert "assert" in second_prompt.lower() or "0 == 2" in second_prompt
    assert "Edit" in second_prompt and "Y" in second_prompt
    assert "Current implementation:" in second_prompt
    assert "return x - 1" in second_prompt
    assert len(second_prompt.split("## Verification", 1)[1]) < 2_000
    assert "===== FAILURES =====" not in second_prompt
    assert "passed" in (result.verification_report or "").lower()
    assert "y.py" in result.final_answer.lower()
    assert "tests passed" in result.final_answer.lower()
    assert "write_file" not in result.final_answer
    assert "read_file" not in str(runner.grammars[1])
    assert "edit_symbol" in str(runner.grammars[1]) or "write_file" in str(runner.grammars[1])
    assert agent.context is not None
    assert any(entry.tool_name == "verification" and not entry.success for entry in agent.context.state.tool_results)
    assert any(entry.tool_name == "verification" and entry.success for entry in agent.context.state.tool_results)


def test_verification_fix_loop_aborts_after_max_attempts(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    writes = [
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": f"def Y(x):\n    return {n}\n"})}>'
        for n in (0, 1, 2)
    ]
    runner = FakeModelRunner(writes)
    agent = Agent(
        runner,
        max_iterations=8,
        verification_root=tmp_path,
        max_fix_attempts=2,
        tool_registry=_tools_only(),
    )
    result = agent.run("Implementiere Funktion Y")

    assert result.stop_reason == StopReason.VERIFICATION_FAILED
    assert result.verification_attempts == 2
    assert "Stopped after 2 failed verification" in result.final_answer
    assert "test_Y" in (result.verification_report or "") or "failed" in result.final_answer.lower()


def test_agent_does_not_complete_before_verification_passes(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    target.write_text("def Y(x):\n    return x - 1\n", encoding="utf-8")
    fixed = "def Y(x):\n    return x + 1\n"
    write_fixed = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": fixed})}>'
    )
    runner = FakeModelRunner(
        [
            "Looks done.",
            write_fixed,
            "Implemented function Y. Verification passed.",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=6,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Implementiere Funktion Y in y.py so that Y(1) == 2.")
    assert result.stop_reason == StopReason.COMPLETED
    assert target.read_text(encoding="utf-8") == fixed
    assert result.metrics.verification_runs >= 1
    assert any("Verification failed" in prompt or "failed" in prompt.lower() for prompt in runner.prompts[1:])
    first_prompt_after_done = runner.prompts[1]
    assert "## Verification" in first_prompt_after_done
    assert "Do not finish yet" in first_prompt_after_done or "Do not give a final answer" in first_prompt_after_done


def test_agent_stops_after_verification_pass_and_ignores_extra_writes(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    target.write_text("def Y(x):\n    return 0\n", encoding="utf-8")
    fixed = "def Y(x):\n    return x + 1\n"
    broken = "def Y(x):\n    return 0\n"
    write_fixed = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": fixed})}>'
    )
    write_broken = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": broken})}>'
    )
    runner = FakeModelRunner([write_fixed, write_broken, "should not be consumed"])
    agent = Agent(
        runner,
        max_iterations=6,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Implementiere Funktion Y")
    assert result.stop_reason == StopReason.COMPLETED
    assert target.read_text(encoding="utf-8") == fixed
    assert result.iterations == 1
    assert result.metrics.verification_runs == 1
    assert result.metrics.verification_failures == 0
    assert runner._outputs == [write_broken, "should not be consumed"]


def test_idle_retry_uses_compact_prompt_and_skips_reasoning(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    target.write_text("def Y(x):\n    return 0\n", encoding="utf-8")
    fixed = "def Y(x):\n    return x + 1\n"
    write_fixed = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": fixed})}>'
    )
    runner = FakeModelRunner(["Looks done.", "Still done.", write_fixed])
    agent = Agent(
        runner,
        max_iterations=6,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Change Y in y.py so that Y(x) returns x + 1.")
    assert result.stop_reason == StopReason.COMPLETED
    assert target.read_text(encoding="utf-8") == fixed
    assert len(runner.prompts) == 3
    assert "Your previous reply had no tool call" in runner.prompts[1]
    assert "Your previous reply had no tool call" in runner.prompts[2]
    assert len(runner.prompts[1]) < len(runner.prompts[0])
    assert result.metrics.reasoning_cycles <= 1
    assert result.metrics.verification_runs >= 2
    assert result.metrics.verification_failures >= 1


def test_edit_symbol_triggers_verification_and_keeps_other_defs(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    target.write_text(
        "PAD = 1\n\ndef Y(x):\n    return 0\n\ndef keep():\n    return 9\n",
        encoding="utf-8",
    )
    call = (
        f'<tool_call=edit_symbol : {json.dumps({"path": str(target), "symbol": "Y", "body": "return x + 1"})}>'
    )
    runner = FakeModelRunner([call])
    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Change Y(x) in y.py so it returns x + 1.")
    assert result.stop_reason == StopReason.COMPLETED
    text = target.read_text(encoding="utf-8")
    assert "return x + 1" in text
    assert "def keep():" in text
    assert "return 9" in text
    assert "PAD = 1" in text
    assert result.metrics.verification_runs == 1
    assert result.metrics.verification_failures == 0
    assert result.iterations == 1


def test_noop_write_does_not_run_verification(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    original = "def Y(x):\n    return 0\n"
    target.write_text(original, encoding="utf-8")
    noop = f'<tool_call=write_file : {json.dumps({"path": str(target), "content": original})}>'
    fixed = "def Y(x):\n    return x + 1\n"
    write_fixed = f'<tool_call=write_file : {json.dumps({"path": str(target), "content": fixed})}>'
    runner = FakeModelRunner([noop, write_fixed])
    agent = Agent(
        runner,
        max_iterations=5,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Change Y in y.py so Y(x) returns x + 1.")
    assert result.stop_reason == StopReason.COMPLETED
    assert target.read_text(encoding="utf-8") == fixed
    assert result.steps[0].tool_results[0].success is False
    assert "file unchanged" in (result.steps[0].tool_results[0].error or "")
    assert result.metrics.verification_runs == 1
    assert result.metrics.verification_failures == 0
    assert "Last write did not change the file" in runner.prompts[1]
    assert "return 0" in runner.prompts[1]


def test_rename_symbol_updates_definition_and_callers(tmp_path: Path) -> None:
    greeter = tmp_path / "greeter.py"
    greeter.write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    app = tmp_path / "app.py"
    app.write_text("from greeter import greet\n\n\ndef run():\n    return greet('Ada')\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from greeter import welcome\nfrom app import run\n\n\n"
        "def test_welcome():\n    assert welcome('Ada') == 'hi Ada'\n    assert run() == 'hi Ada'\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (tmp_path / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )
    call = (
        f'<tool_call=rename_symbol : {json.dumps({"old_name": "greet", "new_name": "welcome", "path": "."})}>'
    )
    runner = FakeModelRunner([call])
    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        max_fix_attempts=3,
        tool_registry=_tools_only(),
    )
    result = agent.run("Rename greet to welcome in greeter.py and update app.py.")
    assert result.stop_reason == StopReason.COMPLETED
    assert "def welcome(" in greeter.read_text(encoding="utf-8")
    app_text = app.read_text(encoding="utf-8")
    assert "welcome" in app_text
    assert "from greeter import welcome" in app_text
    assert "import greet" not in app_text
    assert result.metrics.verification_runs == 1
    assert result.metrics.verification_failures == 0
    assert "rename_symbol" in str(runner.grammars[0])


def test_rename_does_not_complete_on_duplicate_function(tmp_path: Path) -> None:
    greeter = tmp_path / "greeter.py"
    greeter.write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    app = tmp_path / "app.py"
    app.write_text("from greeter import greet\n\n\ndef run():\n    return greet('Ada')\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from greeter import welcome\nfrom app import run\n\n\n"
        "def test_welcome():\n    assert welcome('Ada') == 'hi Ada'\n    assert run() == 'hi Ada'\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (tmp_path / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )
    add_welcome = (
        f'<tool_call=edit_symbol : {json.dumps({"path": str(greeter), "symbol": "welcome", "body": "def welcome(name):\n    return f\'hi {name}\'\n"})}>'
    )
    runner = FakeModelRunner([add_welcome])
    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        max_fix_attempts=3,
        tool_registry=_tools_only(),
    )
    result = agent.run("Rename greet to welcome in greeter.py and update app.py.")
    assert result.stop_reason == StopReason.COMPLETED
    assert "from greeter import welcome" in app.read_text(encoding="utf-8")
    assert "def greet(" not in greeter.read_text(encoding="utf-8")
    assert result.metrics.verification_runs >= 2


def test_rename_repairs_callers_after_definition_only_edit(tmp_path: Path) -> None:
    greeter = tmp_path / "greeter.py"
    greeter.write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    app = tmp_path / "app.py"
    app.write_text("from greeter import greet\n\n\ndef run():\n    return greet('Ada')\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from greeter import welcome\nfrom app import run\n\n\n"
        "def test_welcome():\n    assert welcome('Ada') == 'hi Ada'\n    assert run() == 'hi Ada'\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (tmp_path / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )
    replace_def = (
        f'<tool_call=write_file : {json.dumps({"path": str(greeter), "content": "def welcome(name):\n    return f\'hi {name}\'\n"})}>'
    )
    runner = FakeModelRunner([replace_def])
    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        max_fix_attempts=3,
        tool_registry=_tools_only(),
    )
    result = agent.run("Rename greet to welcome in greeter.py and update app.py.")
    assert result.stop_reason == StopReason.COMPLETED
    assert "from greeter import welcome" in app.read_text(encoding="utf-8")
    assert "return welcome('Ada')" in app.read_text(encoding="utf-8")
    assert "def welcome(" in greeter.read_text(encoding="utf-8")


def test_edit_symbol_creates_missing_helper(tmp_path: Path) -> None:
    names = tmp_path / "names.py"
    names.write_text(
        "def clean_name(text):\n    return (text or '').strip().lower()\n\n\n"
        "def clean_title(text):\n    return (text or '').strip().lower()\n",
        encoding="utf-8",
    )
    (tmp_path / "test_names.py").write_text(
        "from names import clean_name, clean_title, normalize\n\n\n"
        "def test_clean():\n"
        "    assert clean_name('  Ada ') == 'ada'\n"
        "    assert clean_title('  Ada ') == 'ada'\n"
        "    assert normalize('  Ada ') == 'ada'\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (tmp_path / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )
    helper = "def normalize(text):\n    return (text or '').strip().lower()\n"
    use_helper = "return normalize(text)"
    calls = "\n".join(
        [
            f'<tool_call=edit_symbol : {json.dumps({"path": str(names), "symbol": "normalize", "body": helper})}>',
            f'<tool_call=edit_symbol : {json.dumps({"path": str(names), "symbol": "clean_name", "body": use_helper})}>',
            f'<tool_call=edit_symbol : {json.dumps({"path": str(names), "symbol": "clean_title", "body": use_helper})}>',
        ]
    )
    runner = FakeModelRunner([calls])
    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        max_fix_attempts=3,
        tool_registry=_tools_only(),
    )
    result = agent.run("Extract normalize(text) in names.py and use it from clean_name and clean_title.")
    assert result.stop_reason == StopReason.COMPLETED
    text = names.read_text(encoding="utf-8")
    assert "def normalize(" in text
    assert text.count("return normalize(text)") == 2
    assert result.metrics.verification_runs == 1
    assert result.metrics.verification_failures == 0


def test_run_tests_executes_suite_then_fix_loop_passes(tmp_path: Path) -> None:
    target = _write_verify_project(tmp_path)
    target.write_text("def Y(x):\n    return 0\n", encoding="utf-8")
    fixed = "def Y(x):\n    return x + 1\n"
    write_fixed = f'<tool_call=write_file : {json.dumps({"path": str(target), "content": fixed})}>'
    runner = FakeModelRunner(["<tool_call=run_tests : {}>", write_fixed])
    agent = Agent(
        runner,
        max_iterations=5,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Change Y in y.py so Y(x) returns x + 1.")
    assert result.stop_reason == StopReason.COMPLETED
    assert target.read_text(encoding="utf-8") == fixed
    assert result.steps[0].tool_calls[0].name == "run_tests"
    assert result.metrics.verification_runs >= 2
    assert result.metrics.verification_failures >= 1
    assert "failed" in runner.prompts[1].lower()
    assert "test_Y" in runner.prompts[1] or "Y(1)" in runner.prompts[1]


def test_syntax_error_is_in_first_prompt_without_pytest(tmp_path: Path) -> None:
    target = tmp_path / "uniqueutil.py"
    target.write_text("def unique(items)\n    return list(items)\n", encoding="utf-8")
    (tmp_path / "test_uniqueutil.py").write_text(
        "from uniqueutil import unique\n\n\ndef test_unique():\n    assert unique([1, 1]) == [1]\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (tmp_path / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )
    runner = FakeModelRunner(["thinking, no tools yet"])
    agent = Agent(
        runner,
        max_iterations=1,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Fix unique() in uniqueutil.py so it keeps first-seen order.")
    assert result.metrics.verification_runs == 0
    prompt = runner.prompts[0]
    assert "does not parse" in prompt.lower() or "syntax" in prompt.lower()
    assert "uniqueutil.py" in prompt
    assert "tests not run" in prompt.lower()


def test_syntax_write_skips_pytest_until_file_parses(tmp_path: Path) -> None:
    target = tmp_path / "uniqueutil.py"
    target.write_text("def unique(items)\n    return list(items)\n", encoding="utf-8")
    (tmp_path / "test_uniqueutil.py").write_text(
        "from uniqueutil import unique\n\n\ndef test_unique():\n    assert unique([1, 1]) == [1]\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (tmp_path / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )
    still_broken = "def unique(items)\n    return []\n"
    fixed = "def unique(items):\n    return list(dict.fromkeys(items))\n"
    runner = FakeModelRunner(
        [
            f'<tool_call=write_file : {json.dumps({"path": str(target), "content": still_broken})}>',
            f'<tool_call=write_file : {json.dumps({"path": str(target), "content": fixed})}>',
        ]
    )
    agent = Agent(
        runner,
        max_iterations=5,
        verification_root=tmp_path,
        max_fix_attempts=5,
        tool_registry=_tools_only(),
    )
    result = agent.run("Fix unique() in uniqueutil.py so it keeps first-seen order.")
    assert result.stop_reason == StopReason.COMPLETED
    assert result.metrics.verification_runs == 1
    assert result.metrics.verification_failures == 0
    assert "syntax_error" in str(result.steps[0].tool_results[0].output)
    assert "does not parse" in runner.prompts[1].lower() or "syntax" in runner.prompts[1].lower()


def _tools_only():
    from mango_tools import create_default_registry

    return create_default_registry()
