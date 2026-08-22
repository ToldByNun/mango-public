from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from mango_agent import Agent, StopReason
from mango_cot import REASONING_MARKER
from mango_tools import parse_tool_calls


@dataclass
class FakeCompletion:
    text: str


class FakeModelRunner:
    def __init__(self, outputs: list[str], reasoning_outputs: list[str] | None = None) -> None:
        self._outputs = list(outputs)
        self._reasoning_outputs = list(reasoning_outputs or [])
        self.prompts: list[str] = []
        self.reasoning_prompts: list[str] = []
        self.grammars: list[object] = []
        self.grammar_triggers: list[object] = []
        self.force_grammars: list[object] = []
        self.thought_max_tokens: list[object] = []
        self.tool_max_tokens: list[object] = []
        self.temperatures: list[object] = []
        self.top_ps: list[object] = []

    def complete(self, prompt: str, **kwargs) -> FakeCompletion:
        if REASONING_MARKER in prompt:
            self.reasoning_prompts.append(prompt)
            if self._reasoning_outputs:
                return FakeCompletion(text=self._reasoning_outputs.pop(0))
            return FakeCompletion(text='{"next_action": "continue"}')
        self.prompts.append(prompt)
        self.grammars.append(kwargs.get("grammar"))
        self.grammar_triggers.append(kwargs.get("grammar_trigger"))
        self.force_grammars.append(kwargs.get("force_grammar"))
        self.thought_max_tokens.append(kwargs.get("thought_max_tokens"))
        self.tool_max_tokens.append(kwargs.get("tool_max_tokens"))
        self.temperatures.append(kwargs.get("temperature"))
        self.top_ps.append(kwargs.get("top_p"))
        if not self._outputs:
            raise RuntimeError("No more fake outputs")
        text = self._outputs.pop(0)
        on_token = kwargs.get("on_token")
        on_phase = kwargs.get("on_phase")
        if callable(on_token):
            split = re.search(r"<tool_call\b", text, flags=re.IGNORECASE)
            if callable(on_phase) and split:
                thought, tool = text[: split.start()], text[split.start() :]
                if thought:
                    on_token(thought)
                on_phase("tool_grammar")
                if tool:
                    on_token(tool)
            else:
                on_token(text)
        return FakeCompletion(text=text)


def test_agent_loop_executes_tools_then_completes(tmp_path) -> None:
    target = tmp_path / "note.txt"
    target.write_text("alpha\n", encoding="utf-8")

    read_call = f'<tool_call=read_file : {json.dumps({"path": str(target)})}>'
    edit_call = (
        f'<tool_call=edit_file : {json.dumps({"path": str(target), "old_string": "alpha", "new_string": "beta"})}>'
    )

    runner = FakeModelRunner(
        [
            f"I will read the file first.\n{read_call}",
            f"Now I'll edit it.\n{edit_call}",
            "Done. Final content is beta.",
        ]
    )
    agent = Agent(runner, max_iterations=5)
    result = agent.run("Read and edit the file.")

    assert result.stop_reason == StopReason.COMPLETED
    assert result.final_answer == "Done. Final content is beta."
    assert len(result.steps) == 3
    assert target.read_text(encoding="utf-8") == "beta\n"
    assert result.steps[0].tool_results[0].success is True
    assert result.steps[1].tool_results[0].success is True
    assert "alpha" in runner.prompts[1]
    assert "## Goal" in runner.prompts[1]
    assert "Read and edit the file." in runner.prompts[1]
    assert "## Tool results" in runner.prompts[1]


def test_agent_returns_immediately_without_tool_calls() -> None:
    runner = FakeModelRunner(["Hello, no tools needed."])
    agent = Agent(runner, max_iterations=3)
    result = agent.run("Say hi.")
    assert result.stop_reason == StopReason.COMPLETED
    assert result.iterations == 1
    assert result.steps[0].tool_calls == []
    assert runner.grammars
    assert isinstance(runner.grammars[0], str)
    assert "final ::=" not in str(runner.grammars[0])
    assert "read_file" in str(runner.grammars[0])
    assert runner.grammar_triggers[0] == "<tool_call="
    assert runner.force_grammars[0] is False
    assert runner.thought_max_tokens[0] == 128
    assert runner.temperatures[0] == 0.1
    assert runner.top_ps[0] == 0.95


def test_verification_grammar_forbids_final_answer_until_green(tmp_path: Path) -> None:
    target = tmp_path / "y.py"
    target.write_text("def Y(x):\n    return 0\n", encoding="utf-8")
    (tmp_path / "test_y.py").write_text(
        "from y import Y\n\n\ndef test_Y():\n    assert Y(1) == 2\n",
        encoding="utf-8",
    )
    import sys

    (tmp_path / "mango.verify.json").write_text(
        json.dumps(
            {
                "test": {
                    "command": f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider",
                    "timeout": 60,
                }
            }
        ),
        encoding="utf-8",
    )
    call = (
        f'<tool_call=edit_symbol : {json.dumps({"path": str(target), "symbol": "Y", "body": "return x + 1"})}>'
    )
    runner = FakeModelRunner([call])
    from mango_tools import create_default_registry

    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Change Y in y.py so Y(x) returns x + 1.")
    assert result.stop_reason == StopReason.COMPLETED
    assert runner.grammars
    grammar = str(runner.grammars[0])
    assert "edit_symbol" in grammar
    assert "final ::=" not in grammar
    assert runner.grammar_triggers[0] == "<tool_call="
    assert runner.force_grammars[0] is True


def test_agent_stops_at_max_iterations() -> None:
    tool_call = '<tool_call=read_file : {"path": "missing.txt"}>'
    runner = FakeModelRunner([tool_call, tool_call, tool_call])
    agent = Agent(runner, max_iterations=2)
    result = agent.run("Keep calling tools.")
    assert result.stop_reason == StopReason.MAX_ITERATIONS
    assert result.iterations == 2


def test_parse_tool_calls_integration() -> None:
    text = '<tool_call=write_file : {"path": "a.txt", "content": "x"}>'
    calls = parse_tool_calls(text)
    assert calls[0].name == "write_file"


def test_agent_rebuilds_budgeted_prompt(tmp_path) -> None:
    target = tmp_path / "blob.txt"
    target.write_text("Z" * 900, encoding="utf-8")
    call = f'<tool_call=read_file : {json.dumps({"path": str(target)})}>'
    runner = FakeModelRunner([call] * 12 + ["done"])
    agent = Agent(runner, max_iterations=20, max_prompt_chars=5_000)
    result = agent.run("Read blob.txt many times, then stop.")

    assert result.stop_reason == StopReason.COMPLETED
    for prompt in runner.prompts:
        assert len(prompt) <= 7_000
        assert "Read blob.txt many times, then stop." in prompt
    assert any("## Tool results" in prompt for prompt in runner.prompts[1:])
    assert agent.context is not None
    assert len(agent.context.state.tool_results) >= 12


def test_reasoning_state_grows_while_action_prompt_stays_compact(tmp_path) -> None:
    good = tmp_path / "ok.txt"
    good.write_text("hello\n", encoding="utf-8")
    missing_a = tmp_path / "missing_a.txt"
    missing_b = tmp_path / "missing_b.txt"

    runner = FakeModelRunner(
        [
            f'<tool_call=read_file : {json.dumps({"path": str(missing_a)})}>',
            f'<tool_call=read_file : {json.dumps({"path": str(missing_b)})}>',
            f'<tool_call=read_file : {json.dumps({"path": str(good)})}>',
            "The file contains hello.",
        ],
        reasoning_outputs=[
            json.dumps(
                {
                    "next_action": "try a different path",
                    "known_facts": ["missing_a.txt does not exist"],
                }
            ),
            json.dumps(
                {
                    "next_action": "read the known good file",
                    "known_facts": ["missing_b.txt also missing"],
                    "decisions": ["stop probing random names"],
                    "assumptions": ["ok.txt is the intended file"],
                    "open_questions": ["are there more missing paths?"],
                    "failed_attempts": ["read missing_a.txt"],
                }
            ),
        ],
    )
    limit = 7_000
    agent = Agent(runner, max_iterations=8, max_prompt_chars=limit)
    result = agent.run("Debug why the greeting file cannot be read, then report its contents.")

    assert result.stop_reason == StopReason.COMPLETED
    assert agent.cot is not None
    reasoning = agent.cot.state
    assert len(reasoning.failed_attempts) >= 2
    assert len(reasoning.known_facts) >= 2
    assert reasoning.next_action
    assert len(runner.reasoning_prompts) >= 2

    full_reasoning = "\n".join(
        reasoning.known_facts
        + reasoning.decisions
        + reasoning.assumptions
        + reasoning.failed_attempts
        + reasoning.open_questions
        + [reasoning.next_action]
    )
    for prompt in runner.prompts:
        assert len(prompt) <= limit
        if "## Compressed reasoning summary" in prompt:
            assert "Debug why the greeting file cannot be read" in prompt
            assert full_reasoning not in prompt
            summary = prompt.split("## Compressed reasoning summary", 1)[1].split("## ", 1)[0]
            assert len(summary) < len(full_reasoning) or len(summary) <= 720
            assert '"open_questions"' not in prompt
            assert '"known_facts"' not in prompt


def fake_web_research(query: str) -> dict:
    blob = "RESEARCH_BLOB " * 300
    return {
        "query": query,
        "results": [
            {
                "title": "json.dumps — JSON encoder",
                "url": "https://docs.python.org/3/library/json.html",
                "snippet": blob + " json.dumps(obj, *, skipkeys=False)",
            }
        ],
    }


def test_main_agent_ask_epistemic_keeps_main_context_compact() -> None:
    runner = FakeModelRunner(
        [
            '<tool_call=ask_epistemic : {"question": "Does json.dumps exist in json, what is the signature?"}>',
            "json.dumps exists; signature json.dumps(obj, *, skipkeys=False).",
        ]
    )
    agent = Agent(runner, max_iterations=6, epistemic_web_backend=fake_web_research)
    result = agent.run("Look up whether json.dumps exists and report its signature.")

    assert result.stop_reason == StopReason.COMPLETED
    assert agent.epistemic is not None
    assert agent.epistemic.last_subagent_steps == 0
    assert agent.context is not None

    main_bodies = [entry.body for entry in agent.context.state.tool_results]
    assert main_bodies
    assert any("json.dumps" in body for body in main_bodies)
    assert all("RESEARCH_BLOB" not in body for body in main_bodies)
    assert all("API Agent" not in body for body in main_bodies)

    later_prompts = [prompt for prompt in runner.prompts if "Look up whether json.dumps exists" in prompt]
    assert later_prompts
    delta_host = later_prompts[-1]
    assert "RESEARCH_BLOB" not in delta_host
    assert "Compressed reasoning summary" in delta_host or "## Tool results" in delta_host
    compact_hits = [body for body in main_bodies if "exists" in body]
    assert compact_hits
    assert len(compact_hits[-1]) < 2_500


def test_agent_uses_codebase_lookup_without_reading_files(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "util.py").write_text(
        "PAD = '" + ("Q" * 400) + "'\n\ndef greet(name):\n    return f'hi {name}'\n",
        encoding="utf-8",
    )
    (app / "main.py").write_text(
        "from app.util import greet\n\ndef run():\n    return greet('world')\n",
        encoding="utf-8",
    )
    (app / "other.py").write_text(
        "from app.util import greet\n\ndef ping():\n    greet('x')\n",
        encoding="utf-8",
    )

    runner = FakeModelRunner(
        [
            '<tool_call=codebase_lookup : {"query": "Wo wird Funktion greet aufgerufen?"}>',
            "greet is called from app/main.py and app/other.py.",
        ]
    )
    agent = Agent(runner, max_iterations=4, codeintel_root=tmp_path)
    result = agent.run("Wo wird Funktion greet aufgerufen?")

    assert result.stop_reason == StopReason.COMPLETED
    assert [call.name for step in result.steps for call in step.tool_calls] == ["codebase_lookup"]
    body = result.steps[0].tool_results[0].output
    assert body["kind"] == "references"
    paths = {item["path"] for item in body["references"]}
    assert "app/main.py" in paths
    assert "app/other.py" in paths
    assert "Q" * 40 not in str(body)
    assert "PAD" not in str(body)


def test_read_file_prompt_uses_ast_slice_not_raw_source(tmp_path: Path) -> None:
    target = tmp_path / "util.py"
    target.write_text(
        "PAD = '" + ("Q" * 400) + "'\n\n"
        "def greet(name):\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = 3\n"
        "    d = 4\n"
        "    e = 5\n"
        "    f = 6\n"
        "    return name\n",
        encoding="utf-8",
    )
    call = f'<tool_call=read_file : {json.dumps({"path": str(target)})}>'
    runner = FakeModelRunner([call, "done"])
    agent = Agent(runner, max_iterations=4, codeintel_root=tmp_path)
    result = agent.run("Change greet(name) in util.py so it returns Hello.")
    assert result.stop_reason == StopReason.COMPLETED
    assert runner.prompts[1]
    prompt = runner.prompts[1]
    assert "## Memory" in prompt
    assert "def greet" in prompt
    assert "Q" * 50 not in prompt
    assert "f = 6" not in prompt
    assert agent.context is not None
    assert not agent.context.state.memory.is_empty()


def test_agent_ingests_tests_into_memory_before_first_complete(tmp_path: Path) -> None:
    (tmp_path / "greet.py").write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    (tmp_path / "test_greet.py").write_text(
        "from greet import greet\n\n\ndef test_greet():\n    assert greet('Ada') == 'Hello, Ada!'\n",
        encoding="utf-8",
    )
    call = f'<tool_call=read_file : {json.dumps({"path": str(tmp_path / "greet.py")})}>'
    runner = FakeModelRunner([call, "done"])
    agent = Agent(runner, max_iterations=3, codeintel_root=tmp_path, verification_root=tmp_path)
    agent.run("Change greet(name) in greet.py so it returns Hello, name.")
    assert runner.prompts
    prompt = runner.prompts[0]
    assert "## Memory" in prompt
    assert "Hello, Ada" in prompt or "test_greet" in prompt


def test_require_tools_does_not_complete_on_first_text_only(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    target = tmp_path / "math_utils.py"
    call = (
        f'<tool_call=write_file : {json.dumps({"path": "math_utils.py", "content": "x = 1\n"})}>'
    )
    runner = FakeModelRunner(["I will create math_utils.py.", call, "Created the file."])
    agent = Agent(
        runner,
        max_iterations=5,
        require_tools=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Create math_utils.py")
    assert result.stop_reason == StopReason.COMPLETED
    assert runner.force_grammars[0] is True
    assert target.read_text(encoding="utf-8") == "x = 1\n"
    assert result.iterations >= 2


def test_truncated_tool_call_retries_instead_of_finishing(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    target = tmp_path / "mathutil.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    truncated = '<tool_call=write_file : {"path": "mathutil.py", "content": "def add'
    read = f'<tool_call=read_file : {json.dumps({"path": "mathutil.py"})}>'
    fix = (
        '<tool_call=edit_file : '
        + json.dumps({"path": "mathutil.py", "old_string": "return a - b", "new_string": "return a + b"})
        + ">"
    )
    runner = FakeModelRunner([truncated, read, fix, "Fixed add()."])
    agent = Agent(
        runner,
        max_iterations=5,
        require_tools=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        verbose=True,
    )
    result = agent.run("Fix add().")
    assert result.stop_reason == StopReason.COMPLETED
    assert "return a + b" in target.read_text(encoding="utf-8")
    assert result.iterations >= 2
    assert any("truncated" in prompt.lower() or "invalid" in prompt.lower() for prompt in runner.prompts[1:])
    assert any(item is not None and int(item) >= 2048 for item in runner.tool_max_tokens)
    assert any(item is not None and int(item) >= 3072 for item in runner.tool_max_tokens[1:])


def test_failed_edit_retries_with_file_hint(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    target = tmp_path / "mathutil.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    read = f'<tool_call=read_file : {json.dumps({"path": "mathutil.py"})}>'
    bad = (
        '<tool_call=edit_file : '
        + json.dumps({"path": "mathutil.py", "old_string": "not-in-file", "new_string": "x"})
        + ">"
    )
    good = (
        '<tool_call=edit_file : '
        + json.dumps({"path": "mathutil.py", "old_string": "return a - b", "new_string": "return a + b"})
        + ">"
    )
    runner = FakeModelRunner([read, bad, good, "Fixed add()."])
    agent = Agent(
        runner,
        max_iterations=5,
        require_tools=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Fix add().")
    assert result.stop_reason == StopReason.COMPLETED
    assert "return a + b" in target.read_text(encoding="utf-8")
    assert any("old_string" in prompt and "failed" in prompt.lower() for prompt in runner.prompts[1:])


def test_action_grammar_locks_required_edit_keys() -> None:
    runner = FakeModelRunner(["Hello, no tools needed."])
    agent = Agent(runner, max_iterations=1)
    agent.run("Say hi.")
    grammar = str(runner.grammars[0])
    assert '"\\"path\\""' in grammar
    assert '"\\"old_string\\""' in grammar
    assert '"edit_file"' in grammar


def test_inspect_before_edit_blocks_hallucinated_test_edit(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    from mango_agent.benchmark.swebench.workspace import SWE_BENCH_DISABLED_TOOLS

    impl = tmp_path / "src"
    impl.mkdir()
    (impl / "rewrite.py").write_text(
        "def is_rewrite_disabled():\n    return False\n",
        encoding="utf-8",
    )
    testing = tmp_path / "testing"
    testing.mkdir()
    (testing / "test_assertrewrite.py").write_text(
        "def test_rewrite():\n    assert True\n",
        encoding="utf-8",
    )
    search = (
        '<tool_call=search_code : '
        + json.dumps({"pattern": "is_rewrite_disabled"})
        + ">"
    )
    bad = (
        '<tool_call=edit_file : '
        + json.dumps(
            {
                "path": str(testing / "test_assertrewrite.py"),
                "old_string": "def is_rewrite_disabled():\n    return None",
                "new_string": "def is_rewrite_disabled():\n    return False",
            }
        )
        + ">"
    )
    good = (
        '<tool_call=read_file : '
        + json.dumps({"path": str(impl / "rewrite.py")})
        + ">"
    )
    fix = (
        '<tool_call=edit_file : '
        + json.dumps(
            {
                "path": str(impl / "rewrite.py"),
                "old_string": "return False",
                "new_string": "return True",
            }
        )
        + ">"
    )
    runner = FakeModelRunner([bad, search, good, fix, "Fixed rewrite."])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        disabled_tools=SWE_BENCH_DISABLED_TOOLS,
        verbose=True,
    )
    result = agent.run("Fix is_rewrite_disabled so it returns True.")
    assert result.stop_reason == StopReason.COMPLETED
    assert "return True" in (impl / "rewrite.py").read_text(encoding="utf-8")
    assert "assert True" in (testing / "test_assertrewrite.py").read_text(encoding="utf-8")
    first_grammar = str(runner.grammars[0])
    assert "search_code" in first_grammar
    # Complete mode keeps edit_file in GBNF; hallucinated edits are blocked at execution.
    assert "edit_file" in first_grammar
    assert any("rewrite.py" in prompt for prompt in runner.prompts[1:])


def test_require_tools_keeps_going_when_goal_asks_for_tests(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    impl_body = "def clamp(v, lo, hi):\n    return lo if v < lo else hi if v > hi else v\n"
    test_body = "from math_utils import clamp\n\ndef test_clamp():\n    assert clamp(5, 0, 10) == 5\n"
    impl = f'<tool_call=write_file : {json.dumps({"path": "math_utils.py", "content": impl_body})}>'
    test = f'<tool_call=write_file : {json.dumps({"path": "test_math_utils.py", "content": test_body})}>'
    tests = "<tool_call=run_tests : {}>"
    runner = FakeModelRunner([impl, test, tests, "all green"])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Create math_utils.py and test_math_utils.py with pytest and run the tests")
    assert result.error is None, result.error
    assert result.stop_reason == StopReason.COMPLETED
    assert (tmp_path / "math_utils.py").is_file()
    assert (tmp_path / "test_math_utils.py").is_file()
    assert True in runner.force_grammars[1:]


def test_tool_json_is_not_streamed_on_thought_channel() -> None:
    seen: list[dict] = []
    runner = FakeModelRunner(
        ['I will inspect first.\n<tool_call=read_file : {"path": "note.txt"}>', "done"],
    )
    agent = Agent(
        runner,
        max_iterations=3,
        require_tools=True,
        on_event=lambda event: seen.append(event),
    )
    agent.run("Read the file.")
    thought_deltas = [
        str(item["payload"].get("delta") or "")
        for item in seen
        if item.get("event") == "agent.token" and item.get("payload", {}).get("channel") == "thought"
    ]
    assert thought_deltas
    assert all("<tool_call=" not in delta for delta in thought_deltas)


def test_xml_tool_markup_is_stripped_from_thought(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    seen: list[dict] = []
    target = tmp_path / "test_rate_limiter.py"
    target.write_text("x = 1\n", encoding="utf-8")
    xml = (
        "I will read the tests. "
        f'<tool_call name="read_file"> {json.dumps({"path": str(target)})} </tool_call>'
    )
    runner = FakeModelRunner([xml, "done", "done", "done"])
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=False,
        on_event=lambda event: seen.append(event),
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Look at test_rate_limiter.py")
    thoughts = [
        str(item["payload"].get("text") or "")
        for item in seen
        if item.get("event") == "agent.token" and item.get("payload", {}).get("channel") == "thought"
    ]
    blob = "\n".join(thoughts)
    assert "<tool_call" not in blob
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert "read_file" in names


def test_require_tools_skips_repo_symbol_lookup(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    calls: list[str] = []

    class SpyIndex:
        root = tmp_path

        def refresh(self, *, force: bool = False) -> dict:
            return {"parsed": 0, "skipped": 0}

        def lookup(self, query: str, *, kind: str = "auto") -> dict:
            calls.append(query)
            return {"definitions": [], "files": []}

    impl_body = "def clamp(v, lo, hi):\n    return v\n"
    impl = f'<tool_call=write_file : {json.dumps({"path": "math_utils.py", "content": impl_body})}>'
    test_body = "from math_utils import clamp\n\ndef test_clamp():\n    assert clamp(1, 0, 2) == 1\n"
    test = f'<tool_call=write_file : {json.dumps({"path": "test_math_utils.py", "content": test_body})}>'
    tests = "<tool_call=run_tests : {}>"
    runner = FakeModelRunner([impl, test, tests, "done"])
    registry = create_default_registry()
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
    )
    agent._codeintel = SpyIndex()  # type: ignore[assignment]
    result = agent.run(
        "Erstelle math_utils.py mit clamp(val, min_val, max_val) und teste mit pytest"
    )
    assert result.stop_reason == StopReason.COMPLETED
    assert calls == []

    runner = FakeModelRunner(["Hello, no tools needed."])
    agent = Agent(runner, max_iterations=3, require_tools=False)
    result = agent.run("Say hi.")
    assert result.stop_reason == StopReason.COMPLETED
    assert result.iterations == 1
    assert runner.force_grammars[0] is False


def test_plan_apis_first_blocks_write_until_epistemic(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    declare = '<tool_call=declare_apis : {"libraries": "pandas, argparse"}>'
    epi = '<tool_call=ask_epistemic : {"question": "How do pandas.read_csv and argparse work?"}>'
    write = '<tool_call=write_file : {"path": "app.py", "content": "print(1)\\n"}>'

    def _ask(question: str, _context=None):
        return {
            "exists": True,
            "details": "pandas.read_csv and argparse.ArgumentParser exist",
            "signature": "read_csv(path)",
        }

    registry = create_default_registry()
    registry.register(
        "ask_epistemic",
        _ask,
        description="stub",
        parameters={"question": {"type": "string"}},
        required=["question"],
    )
    runner = FakeModelRunner([write, declare, epi, write, "done"])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
        use_tool_grammar=True,
    )
    result = agent.run("Create a pandas CSV CLI")

    assert result.stop_reason == StopReason.COMPLETED
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    first = result.steps[0].tool_results[0]
    assert first.success is False
    assert "declare_apis" in (first.error or "")
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names[:3] == ["write_file", "declare_apis", "ask_epistemic"]
    grammars = [str(item) for item in runner.grammars if item]
    # Complete mode: write_file stays in grammar; plan gate blocks execution until declare/epistemic.
    assert any("declare_apis" in item and "write_file" in item for item in grammars[:1])
    assert any("ask_epistemic" in item for item in grammars)


def test_plan_apis_ignores_unittest_and_uses_declared_lookups(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    declare = '<tool_call=declare_apis : {"libraries": "collections, threading, time, unittest, unittest.mock"}>'
    vague = '<tool_call=ask_epistemic : {"question": "How should the sliding window work?"}>'
    write = '<tool_call=write_file : {"path": "app.py", "content": "print(1)\\n"}>'

    def _ask(question: str, _context=None):
        libs = (_context or {}).get("declared_libraries") or []
        return {
            "exists": True,
            "details": "from collections import deque; Lock() per client; time.monotonic()",
            "signature": "deque.append(x)",
            "looked_up": ["collections.deque", "threading.Lock", "time.monotonic"],
            "declared": libs,
        }

    registry = create_default_registry()
    registry.register(
        "ask_epistemic",
        _ask,
        description="stub",
        parameters={"question": {"type": "string"}},
        required=["question"],
    )
    runner = FakeModelRunner([declare, vague, write, "done"])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
        use_tool_grammar=True,
    )
    result = agent.run("Build a rate limiter")
    assert result.stop_reason == StopReason.COMPLETED
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names.count("ask_epistemic") == 1
    assert "write_file" in names


def test_plan_apis_ignores_uuid_traceback_and_locks_write_file(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    declare = (
        '<tool_call=declare_apis : {"libraries": '
        '"uuid, threading, concurrent.futures, collections, traceback, time"}>'
    )
    vague = '<tool_call=ask_epistemic : {"question": "How should the event bus work?"}>'
    write = '<tool_call=write_file : {"path": "event_bus.py", "content": "x = 1\\n"}>'

    def _ask(question: str, _context=None):
        return {
            "exists": True,
            "details": "ThreadPoolExecutor + Lock per topic + deque(maxlen=50)",
            "signature": "ThreadPoolExecutor(max_workers=8)",
            "looked_up": [
                "concurrent.futures.ThreadPoolExecutor",
                "threading.Lock",
                "collections.deque",
                "time.monotonic",
            ],
        }

    registry = create_default_registry()
    registry.register(
        "ask_epistemic",
        _ask,
        description="stub",
        parameters={"question": {"type": "string"}},
        required=["question"],
    )
    runner = FakeModelRunner([declare, vague, write, "done"])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
        use_tool_grammar=True,
    )
    result = agent.run("Build an event bus")
    assert result.stop_reason == StopReason.COMPLETED, result.error
    assert (tmp_path / "event_bus.py").read_text(encoding="utf-8") == "x = 1\n"
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names.count("ask_epistemic") == 1
    assert names.count("write_file") == 1
    write_turn = str(runner.grammars[2] or "")
    assert "write_file" in write_turn
    # Complete mode may still list ask_epistemic; preference steers toward write_file.


def test_missing_tests_prefer_write_file_over_run_tests(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    impl = '<tool_call=write_file : {"path": "app.py", "content": "def add(a, b):\\n    return a + b\\n"}>'
    tests = (
        '<tool_call=write_file : {"path": "test_app.py", "content": '
        '"from app import add\\n\\ndef test_add():\\n    assert add(1, 1) == 2\\n"}>'
    )
    runner = FakeModelRunner([impl, tests, "done"])
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        task_wants_tests=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        use_tool_grammar=True,
    )
    result = agent.run("Create add() and tests")
    assert result.stop_reason == StopReason.COMPLETED
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names[:2] == ["write_file", "write_file"]
    assert (tmp_path / "test_app.py").is_file()
    second = str(runner.grammars[1] or "")
    assert second.lstrip().startswith("root ::= (write-file-full")


def test_plan_apis_first_requires_every_declared_name(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    declare = '<tool_call=declare_apis : {"libraries": "pandas, numpy"}>'
    partial = '<tool_call=ask_epistemic : {"question": "How does pandas.read_csv work?"}>'
    full = '<tool_call=ask_epistemic : {"question": "How do pandas.read_csv and numpy.array work?"}>'
    write = '<tool_call=write_file : {"path": "app.py", "content": "print(1)\\n"}>'

    def _ask(question: str, _context=None):
        return {"exists": True, "details": question, "signature": "read_csv(path)"}

    registry = create_default_registry()
    registry.register(
        "ask_epistemic",
        _ask,
        description="stub",
        parameters={"question": {"type": "string"}},
        required=["question"],
    )
    runner = FakeModelRunner([declare, partial, write, full, write, "done"])
    agent = Agent(
        runner,
        max_iterations=10,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
        use_tool_grammar=True,
    )
    result = agent.run("Create a pandas numpy CSV tool")

    assert result.stop_reason == StopReason.COMPLETED
    blocked_write = next(
        item
        for step in result.steps
        for item in step.tool_results
        if item.tool_name == "write_file"
    )
    assert blocked_write.success is False
    assert "BLOCKED" in (blocked_write.error or "")
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print(1)\n"


def test_plan_apis_skips_epistemic_for_stdlib_csv_cli(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    write = '<tool_call=write_file : {"path": "csv_sum.py", "content": "print(1)\\n"}>'
    runner = FakeModelRunner([write, "done"])
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        use_tool_grammar=True,
    )
    result = agent.run("CSV CLI with argparse csv pathlib")
    assert result.stop_reason == StopReason.COMPLETED, result.error
    assert (tmp_path / "csv_sum.py").read_text(encoding="utf-8") == "print(1)\n"
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names[0] == "write_file"
    assert "ask_epistemic" not in names
    assert "declare_apis" not in names
    first_grammar = str(runner.grammars[0] or "")
    assert "write_file" in first_grammar


def test_plan_apis_follow_up_allows_read_then_epistemic(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    target = tmp_path / "rate_limiter.py"
    target.write_text("class SlidingWindowLimiter:\n    pass\n", encoding="utf-8")
    read = f'<tool_call=read_file : {json.dumps({"path": str(target)})}>'
    epi = '<tool_call=ask_epistemic : {"question": "What is threading.Lock()?"}>'
    write = '<tool_call=write_file : {"path": "rate_limiter.py", "content": "x = 1\\n"}>'

    def _ask(question: str, _context=None):
        return {"exists": True, "details": "threading.Lock", "signature": "Lock()"}

    registry = create_default_registry()
    registry.register(
        "ask_epistemic",
        _ask,
        description="stub",
        parameters={"question": {"type": "string"}},
        required=["question"],
    )
    runner = FakeModelRunner([read, epi, write, "done"])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
        use_tool_grammar=True,
    )
    result = agent.run(
        "You already changed files in this workspace for an earlier request.\n"
        "Original request:\nBuild a rate limiter\n\n"
        "Follow-up request:\nReview concurrency bottlenecks\n"
    )

    assert result.stop_reason == StopReason.COMPLETED, result.error
    first = result.steps[0].tool_results[0]
    assert first.tool_name == "read_file"
    assert first.success is True
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names[:2] == ["read_file", "ask_epistemic"]
    assert target.read_text(encoding="utf-8") == "x = 1\n"
    grammars = [str(item) for item in runner.grammars if item]
    # Complete mode keeps write_file in GBNF; steering is via preferred feedback / plan gate.
    assert any("read_file" in item for item in grammars[:1])
    assert any("ask_epistemic" in item for item in grammars[:1])
    # Legacy strip characterization (rollback path).
    import os

    os.environ["MANGO_TOOL_FILTER_MODE"] = "legacy"
    try:
        legacy_names = agent._action_tool_names_legacy()
        # Follow-up inspect path in legacy may exclude write_file.
        assert "read_file" in legacy_names or "ask_epistemic" in legacy_names
    finally:
        os.environ.pop("MANGO_TOOL_FILTER_MODE", None)


def test_write_file_syntax_error_blocks_finish(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    bad = '<tool_call=write_file : {"path": "app.py", "content": "print(1).\\n"}>'
    good = '<tool_call=write_file : {"path": "app.py", "content": "print(1)\\n"}>'
    runner = FakeModelRunner([bad, "All done.", good, "Fixed the syntax error."])
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Create app.py that prints 1")

    assert result.stop_reason == StopReason.COMPLETED
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print(1)\n"
    assert result.iterations >= 3
    assert result.steps[1].tool_calls == []


def test_truncated_write_restores_last_compiling_file(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    good = '<tool_call=write_file : {"path": "app.py", "content": "x = 1\\n"}>'
    bad = '<tool_call=write_file : {"path": "app.py", "content": "def broken(\\n"}>'
    tests = (
        '<tool_call=write_file : {"path": "test_app.py", "content": '
        '"def test_ok():\\n    import app\\n    assert app.x == 1\\n"}>'
    )
    runner = FakeModelRunner([good, bad, tests, "done"])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Create app.py and tests")
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "x = 1\n"
    assert result.stop_reason == StopReason.COMPLETED


def test_failed_tests_do_not_abort_after_two_attempts(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    bad = "def add(a, b):\n    return a - b\n"
    test = "from app import add\n\ndef test_add():\n    assert add(1, 1) == 2\n"
    good = "def add(a, b):\n    return a + b\n"
    runner = FakeModelRunner(
        [
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": bad})}>',
            f'<tool_call=write_file : {json.dumps({"path": "test_app.py", "content": test})}>',
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": good})}>',
            "Fixed the tests.",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Create add() and tests")
    assert "Stopping to avoid an infinite retry loop" not in (result.error or "")
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == good
    assert result.stop_reason == StopReason.COMPLETED


def test_many_failed_pytest_runs_stop_at_iteration_limit(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    (tmp_path / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(1, 1) == 2\n",
        encoding="utf-8",
    )
    bad = "def add(a, b):\n    return a - b\n"
    runner = FakeModelRunner(
        [
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": bad})}>',
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": bad + "# try2\\n"})}>',
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": bad + "# try3\\n"})}>',
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": bad + "# try4\\n"})}>',
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": bad + "# try5\\n"})}>',
            "I am done.",
            "I am done.",
            "I am done.",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Fix add() so tests pass")
    assert result.stop_reason in {StopReason.MAX_ITERATIONS, StopReason.ERROR}
    assert not result.final_answer.lower().startswith("i am done")
    assert "stopping the fix loop" not in (result.final_answer or "").lower()
    assert "failed after 5 automatic" not in (result.final_answer or "").lower()


def test_concurrent_code_requires_thread_stress_test(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    impl = (
        "import threading\n"
        "_lock = threading.Lock()\n"
        "_n = 0\n"
        "def bump():\n"
        "    global _n\n"
        "    with _lock:\n"
        "        _n += 1\n"
        "        return _n\n"
    )
    tests = "from app import bump\n\ndef test_bump():\n    assert bump() >= 1\n"
    runner = FakeModelRunner(
        [
            f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": impl})}>',
            f'<tool_call=write_file : {json.dumps({"path": "test_app.py", "content": tests})}>',
            "done",
            "done",
            f'<tool_call=read_file : {json.dumps({"path": "app.py"})}>',
            "The lock still covers the shared counter. Done.",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=12,
        require_tools=True,
        task_wants_tests=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Create a thread-safe bump() with tests")
    assert any("ThreadPoolExecutor" in prompt for prompt in runner.prompts)
    assert result.stop_reason == StopReason.COMPLETED


def test_lock_coarsen_forces_reread_and_doubt(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    per_client = (
        "from collections import defaultdict\n"
        "from threading import Lock\n\n"
        "class SlidingWindowLimiter:\n"
        "    def __init__(self, max_requests, window_seconds):\n"
        "        self.max_requests = max_requests\n"
        "        self.window_seconds = window_seconds\n"
        "        self.clients = defaultdict(list)\n"
        "        self.locks = defaultdict(Lock)\n\n"
        "    def allow(self, client_id):\n"
        "        with self.locks[client_id]:\n"
        "            self.clients[client_id].append(0)\n"
        "            return len(self.clients[client_id]) <= self.max_requests\n"
    )
    global_lock = (
        "from collections import defaultdict\n"
        "from threading import Lock\n\n"
        "class SlidingWindowLimiter:\n"
        "    def __init__(self, max_requests, window_seconds):\n"
        "        self.max_requests = max_requests\n"
        "        self.window_seconds = window_seconds\n"
        "        self.clients = defaultdict(list)\n"
        "        self.lock = Lock()\n\n"
        "    def allow(self, client_id):\n"
        "        with self.lock:\n"
        "            self.clients[client_id].append(0)\n"
        "            return len(self.clients[client_id]) <= self.max_requests\n"
    )
    tests = (
        "from concurrent.futures import ThreadPoolExecutor\n"
        "from limiter import SlidingWindowLimiter\n\n"
        "def test_allow():\n"
        "    lim = SlidingWindowLimiter(10, 1)\n"
        "    assert lim.allow('a') is True\n\n"
        "def test_threads():\n"
        "    lim = SlidingWindowLimiter(1000, 5)\n"
        "    with ThreadPoolExecutor(max_workers=8) as pool:\n"
        "        list(pool.map(lambda i: lim.allow(str(i % 3)), range(40)))\n"
    )
    (tmp_path / "limiter.py").write_text(per_client, encoding="utf-8")
    (tmp_path / "test_limiter.py").write_text(tests, encoding="utf-8")
    read = f'<tool_call=read_file : {json.dumps({"path": "limiter.py"})}>'
    runner = FakeModelRunner(
        [
            read,
            f'<tool_call=write_file : {json.dumps({"path": "limiter.py", "content": global_lock})}>',
            f'<tool_call=read_file : {json.dumps({"path": "limiter.py"})}>',
            "Keeping the global lock. Done.",
            "Keeping the global lock. Done.",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Harden the rate limiter")
    blob = "\n".join(runner.prompts)
    assert "per-client" in blob.lower() or "global lock" in blob.lower()
    assert result.stop_reason == StopReason.COMPLETED
    assert (tmp_path / "limiter.py").read_text(encoding="utf-8") == global_lock


def test_failed_edit_falls_back_to_write_file(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    original = "import os\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n"
    rewritten = "import os\n\ndef a():\n    return 9\n\ndef b():\n    return 2\n"
    (tmp_path / "app.py").write_text(original, encoding="utf-8")
    read = f'<tool_call=read_file : {json.dumps({"path": "app.py"})}>'
    edit = {
        "path": "app.py",
        "old_string": "this snippet is not in the file at all",
        "new_string": rewritten,
    }
    runner = FakeModelRunner(
        [
            read,
            f"<tool_call=edit_file : {json.dumps(edit)}>",
            "Done. Rewrote the file.",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=4,
        require_tools=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Change a() to return 9")
    assert result.stop_reason == StopReason.COMPLETED
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == rewritten


def test_code_fence_in_thought_is_stripped(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    seen: list[dict] = []
    body = "print(1)\n"
    thought = "```python\nimport sys\ndef main():\n    pass\n```\n"
    call = f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": body})}>'
    runner = FakeModelRunner([thought + call, "done"])
    agent = Agent(
        runner,
        max_iterations=4,
        require_tools=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        on_event=lambda event: seen.append(event),
    )
    result = agent.run("Create app.py")
    assert result.stop_reason == StopReason.COMPLETED
    done_thoughts = [
        item["payload"].get("text", "")
        for item in seen
        if item.get("event") == "agent.token"
        and item.get("payload", {}).get("done")
        and item.get("payload", {}).get("channel") == "thought"
    ]
    blob = "\n".join(str(text) for text in done_thoughts)
    assert "def main" not in blob
    assert "```" not in blob


def test_cot_thought_event_is_not_chain_dump(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    missing = tmp_path / "missing.py"
    seen: list[dict] = []
    write = f'<tool_call=write_file : {json.dumps({"path": str(tmp_path / "ok.py"), "content": "x = 1\\n"})}>'
    runner = FakeModelRunner(
        [
            f'<tool_call=read_file : {json.dumps({"path": str(missing)})}>',
            write,
            "done",
        ],
        reasoning_outputs=[
            '{"next_action": "write_file", "known_facts": ["the file is missing"]}',
        ],
    )
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        on_event=lambda event: seen.append(event),
        max_reasoning_cycles=4,
    )
    agent.run("Create ok.py")
    thoughts = [
        str(item["payload"].get("text") or "")
        for item in seen
        if item.get("event") == "agent.thought"
    ]
    blob = "\n".join(thoughts)
    assert "Chain:" not in blob
    assert "thought2:" not in blob
    if thoughts:
        assert "write_file" in blob or "missing" in blob.lower()


def test_plan_apis_first_skips_cot_cycles(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    declare = '<tool_call=declare_apis : {"libraries": "json"}>'
    epi = '<tool_call=ask_epistemic : {"question": "How does json.dumps work?"}>'
    write = '<tool_call=write_file : {"path": "app.py", "content": "x = 1\\n"}>'

    def _ask(question: str, _context=None):
        return {
            "exists": True,
            "details": "json.dumps(obj, *, skipkeys=False) serializes obj to a JSON str.",
            "signature": "json.dumps(obj)",
        }

    registry = create_default_registry()
    registry.register(
        "ask_epistemic",
        _ask,
        description="stub",
        parameters={"question": {"type": "string"}},
        required=["question"],
    )
    runner = FakeModelRunner(
        [declare, epi, write, "done"],
        reasoning_outputs=['{"next_action": "write_file"}'],
    )
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
        max_reasoning_cycles=8,
    )
    result = agent.run("Create app.py")
    assert result.stop_reason == StopReason.COMPLETED
    assert runner.reasoning_prompts == []
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "x = 1\n"


def test_thought_budget_stays_at_configured_cap(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    missing = tmp_path / "missing.py"
    write = f'<tool_call=write_file : {json.dumps({"path": str(tmp_path / "ok.py"), "content": "x = 1\\n"})}>'
    runner = FakeModelRunner(
        [
            f'<tool_call=read_file : {json.dumps({"path": str(missing)})}>',
            write,
            "done",
        ]
    )
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        task_wants_tests=False,
        thought_max_tokens=192,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    agent.run("Create ok.py")
    assert runner.thought_max_tokens
    assert all(item is None or int(item) <= 192 for item in runner.thought_max_tokens)
    assert runner.tool_max_tokens
    assert any(item is not None and int(item) >= 2048 for item in runner.tool_max_tokens)


def test_thinking_level_sets_thought_budget_and_prompt() -> None:
    runner = FakeModelRunner(["Hello, no tools needed."])
    agent = Agent(runner, max_iterations=2, thinking_level="deep")
    agent.run("Say hi.")
    assert runner.thought_max_tokens
    assert runner.thought_max_tokens[0] == 384
    assert "Thinking level: deep" in agent._system_prompt


def test_write_file_turn_uses_large_tool_budget(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    write = f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": "x = 1\\n"})}>'
    runner = FakeModelRunner([write, "done"])
    agent = Agent(
        runner,
        max_iterations=4,
        require_tools=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    agent.run("Create app.py")
    assert runner.tool_max_tokens
    assert all(item is not None and int(item) >= 2048 for item in runner.tool_max_tokens)


def test_edit_auto_runs_tests_instead_of_stopping(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    (tmp_path / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(1, 1) == 2\n",
        encoding="utf-8",
    )
    edit = (
        f'<tool_call=edit_file : {json.dumps({"path": "app.py", "old_string": "return a - b", "new_string": "return a + b"})}>'
    )
    read = f'<tool_call=read_file : {json.dumps({"path": "app.py"})}>'
    runner = FakeModelRunner([read, edit, "Fixed add() with passing tests."])
    agent = Agent(
        runner,
        max_iterations=4,
        require_tools=True,
        task_wants_tests=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Fix add()")
    names = [item.tool_name for step in result.steps for item in step.tool_results]
    assert "run_tests" in names
    assert result.stop_reason == StopReason.COMPLETED
    assert "All tests passed." != result.final_answer
    assert "app.py" in result.final_answer
    assert "test" in result.final_answer.lower()
    assert (tmp_path / "app.py").read_text(encoding="utf-8").count("return a + b") == 1


def test_api_catalog_dump_is_stripped_from_thought() -> None:
    seen: list[dict] = []
    dump = (
        "threading.get_ident() | threading.active_count() | threading.Condition() | "
        "threading.current_thread() | threading.Lock() | threading.RLock()"
    )
    runner = FakeModelRunner(
        [f"I will inspect first. {dump}\n<tool_call=read_file : {json.dumps({'path': 'missing.py'})}>", "done"],
    )
    agent = Agent(
        runner,
        max_iterations=3,
        require_tools=False,
        on_event=lambda event: seen.append(event),
    )
    agent.run("Read missing.py")
    done_thoughts = [
        str(item["payload"].get("text") or "")
        for item in seen
        if item.get("event") == "agent.token" and item.get("payload", {}).get("done")
    ]
    blob = "\n".join(done_thoughts)
    assert "active_count" not in blob
    assert "get_ident" not in blob


def test_finish_summary_uses_model_text_when_plan_gate_on(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    (tmp_path / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(1, 1) == 2\n",
        encoding="utf-8",
    )
    edit = (
        f'<tool_call=edit_file : {json.dumps({"path": "app.py", "old_string": "return a - b", "new_string": "return a + b"})}>'
    )
    read = f'<tool_call=read_file : {json.dumps({"path": "app.py"})}>'
    summary = (
        "I changed app.py so add() returns a plus b instead of a minus b.\n\n"
        "That matches the requested arithmetic.\n\n"
        "Tests passed.\n\n"
        "A later follow-up should read app.py and test_app.py before editing."
    )
    runner = FakeModelRunner([read, edit, summary])
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        task_wants_tests=True,
        plan_apis_first=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run(
        "You already changed files in this workspace for an earlier request.\n"
        "Original request:\nCreate add()\n\n"
        "Follow-up request:\nFix add()\n"
    )
    assert result.stop_reason == StopReason.COMPLETED
    assert "plus b" in result.final_answer
    assert "All tests passed." not in result.final_answer


def test_thought_ids_differ_across_runs() -> None:
    seen: list[dict] = []
    read = '<tool_call=read_file : {"path": "missing.py"}>'
    runner = FakeModelRunner([read, "done", read, "done"])
    agent = Agent(
        runner,
        max_iterations=3,
        require_tools=False,
        on_event=lambda event: seen.append(event),
    )
    agent.run("first")
    first = [
        str(item["payload"].get("id") or "")
        for item in seen
        if item.get("event") == "agent.token"
    ]
    seen.clear()
    agent.run("second")
    second = [
        str(item["payload"].get("id") or "")
        for item in seen
        if item.get("event") == "agent.token"
    ]
    assert first and second
    assert set(first).isdisjoint(set(second))


def test_gui_grounded_blocks_edit_without_read(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    impl = tmp_path / "src"
    impl.mkdir()
    (impl / "foo.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    bad = (
        '<tool_call=edit_file : '
        + json.dumps({"path": str(impl / "foo.py"), "old_string": "return 1", "new_string": "return 2"})
        + ">"
    )
    read = f'<tool_call=read_file : {json.dumps({"path": str(impl / "foo.py")})}>'
    good = (
        '<tool_call=edit_file : '
        + json.dumps({"path": str(impl / "foo.py"), "old_string": "return 1", "new_string": "return 2"})
        + ">"
    )
    runner = FakeModelRunner([bad, read, good, "Updated foo."])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=False,
        plan_apis_first=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Change foo() to return 2.")
    assert result.stop_reason == StopReason.COMPLETED
    assert "return 2" in (impl / "foo.py").read_text(encoding="utf-8")
    blocked = [
        item
        for step in result.steps
        for item in step.tool_results
        if not item.success and "BLOCKED" in str(item.error or "")
    ]
    assert blocked
    # Complete mode keeps edit_file in GBNF; grounding is enforced by the runner block.
    assert "edit_file" in str(runner.grammars[0])
    assert "read_file" in str(runner.grammars[0])


def test_gui_grounded_blocks_test_edit_before_impl(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    impl = tmp_path / "src"
    impl.mkdir()
    (impl / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text("def test_value():\n    assert True\n", encoding="utf-8")
    bad = (
        '<tool_call=edit_file : '
        + json.dumps({"path": str(tests / "test_app.py"), "old_string": "assert True", "new_string": "assert False"})
        + ">"
    )
    read = f'<tool_call=read_file : {json.dumps({"path": str(impl / "app.py")})}>'
    good = (
        '<tool_call=edit_file : '
        + json.dumps({"path": str(impl / "app.py"), "old_string": "return 1", "new_string": "return 2"})
        + ">"
    )
    runner = FakeModelRunner([bad, read, good, "Fixed impl."])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=False,
        plan_apis_first=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Fix value() to return 2.")
    assert result.stop_reason == StopReason.COMPLETED
    assert "return 2" in (impl / "app.py").read_text(encoding="utf-8")
    assert "assert False" not in (tests / "test_app.py").read_text(encoding="utf-8")


def test_greenfield_skips_grounded_explore(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    body = "def greet():\n    return 'hi'\n"
    write = f'<tool_call=write_file : {json.dumps({"path": "greet.py", "content": body})}>'
    runner = FakeModelRunner([write, "Created greet.py."])
    agent = Agent(
        runner,
        max_iterations=6,
        require_tools=True,
        task_wants_tests=False,
        plan_apis_first=True,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Create greet.py with greet().")
    assert result.stop_reason in {StopReason.COMPLETED, StopReason.ERROR}
    first_grammar = str(runner.grammars[0])
    assert "declare_apis" in first_grammar or "write_file" in first_grammar


def test_grounded_rejects_fuzzy_edit_without_read(tmp_path: Path) -> None:
    from mango_tools import create_default_registry

    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    fuzzy = (
        '<tool_call=edit_file : '
        + json.dumps(
            {
                "path": "calc.py",
                "old_string": "def add(a, b):\n    return a - b",
                "new_string": "def add(a, b):\n    return a + b",
            }
        )
        + ">"
    )
    read = f'<tool_call=read_file : {json.dumps({"path": "calc.py"})}>'
    exact = (
        '<tool_call=edit_file : '
        + json.dumps({"path": "calc.py", "old_string": "return a - b", "new_string": "return a + b"})
        + ">"
    )
    runner = FakeModelRunner([fuzzy, read, exact, "Fixed add."])
    agent = Agent(
        runner,
        max_iterations=8,
        require_tools=True,
        task_wants_tests=False,
        plan_apis_first=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Fix add().")
    assert result.stop_reason == StopReason.COMPLETED
    assert "return a + b" in target.read_text(encoding="utf-8")
    blocked = any(
        not item.success and "BLOCKED" in str(item.error or "")
        for step in result.steps
        for item in step.tool_results
    )
    assert blocked


