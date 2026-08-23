from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mango_agent import Agent, StopReason
from mango_cot import REASONING_MARKER


@dataclass
class FakeCompletion:
    text: str


class FakeModelRunner:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.prompts: list[str] = []
        self.action_prompts: list[str] = []

    def complete(self, prompt: str, **kwargs) -> FakeCompletion:
        self.prompts.append(prompt)
        # Chained CoT / reasoning cycles — never consume action script outputs.
        if REASONING_MARKER in prompt or "cot_chain" in prompt.lower() or "prior_steps" in prompt:
            return FakeCompletion(
                text='{"summary":"Inspected workspace files.","next_action":"answer","known_facts":[]}'
            )
        self.action_prompts.append(prompt)
        if not self._outputs:
            raise RuntimeError("No more fake outputs")
        return FakeCompletion(text=self._outputs.pop(0))


def _ask_agent(runner: FakeModelRunner, **kwargs) -> Agent:
    defaults = dict(
        max_iterations=1,
        require_tools=True,
        plan_mode=True,
        agent_mode="ask",
        task_wants_tests=False,
        plan_apis_first=False,
        enable_declare_apis=False,
    )
    defaults.update(kwargs)
    return Agent(runner, **defaults)


def test_ask_mode_only_file_tools() -> None:
    agent = _ask_agent(FakeModelRunner(["done"]))
    names = agent._action_tool_names()
    assert names[0] in {"list_dir", "glob_files", "search_code", "read_file"}
    assert "ask_epistemic" not in names
    assert "research_codebase" not in names
    assert "codebase_lookup" not in names
    assert "write_file" not in names
    assert "run_tests" not in names
    assert "declare_apis" not in names


def test_ask_forces_tools_until_read() -> None:
    agent = _ask_agent(FakeModelRunner(["done"]))
    assert agent._needs_tool() is True
    agent._acted_once = True  # empty list/glob alone must NOT unlock assistant dump
    assert agent._needs_tool() is True
    agent._inspected_once = True
    assert agent._finish_allowed() is True
    assert agent._needs_tool() is False


def test_ask_skips_chained_cot_before_reads(tmp_path: Path) -> None:
    target = tmp_path / "note.py"
    target.write_text("X = 1\n", encoding="utf-8")
    listed = f'<tool_call=list_dir : {json.dumps({"path": str(tmp_path)})}>'
    read = f'<tool_call=read_file : {json.dumps({"path": str(target)})}>'
    runner = FakeModelRunner(
        [
            f"List.\n{listed}",
            f"Read.\n{read}",
            "X is 1 in note.py.",
        ]
    )
    agent = _ask_agent(
        runner,
        max_iterations=8,
        verification_root=tmp_path,
        codeintel_root=tmp_path,
    )
    import mango_cot.cot_engine as cot_mod

    call_log: list[str] = []
    original = cot_mod.CoTEngine.run_chained

    def _wrapped(self, *args, **kwargs):
        inspected_before = bool(getattr(agent, "_inspected_once", False))
        call_log.append("after_read" if inspected_before else "before_read")
        return original(self, *args, **kwargs)

    cot_mod.CoTEngine.run_chained = _wrapped  # type: ignore[method-assign]
    try:
        result = agent.run("what is X?")
    finally:
        cot_mod.CoTEngine.run_chained = original  # type: ignore[method-assign]

    assert result.stop_reason == StopReason.COMPLETED
    assert "before_read" not in call_log
    used = [tr.tool_name for step in result.steps for tr in step.tool_results]
    assert "read_file" in used


def test_ask_finish_rejects_feedback_template_leak() -> None:
    agent = _ask_agent(FakeModelRunner(["done"]))
    junk = (
        "# (unused — finish text is built in Python as plain f-strings "
        "to avoid unfilled {{placeholders}})"
    )
    summary = agent._write_finish_summary([], draft=junk)
    assert "{{" not in summary
    assert "unused" not in summary.lower()
    assert "Ask finished." in summary


def test_ask_mode_reads_files_not_epistemic(tmp_path: Path) -> None:
    target = tmp_path / "commands.py"
    target.write_text(
        "COMMANDS = {\n"
        "  'list_dir': ['path'],\n"
        "  'read_file': ['path', 'offset', 'limit'],\n"
        "}\n",
        encoding="utf-8",
    )
    epi = '<tool_call=ask_epistemic : {"question": "what command types exist?"}>'
    listed = f'<tool_call=list_dir : {json.dumps({"path": str(tmp_path)})}>'
    read = f'<tool_call=read_file : {json.dumps({"path": str(target)})}>'
    answer = (
        "Command types already present: list_dir(path), "
        "read_file(path, offset, limit)."
    )
    runner = FakeModelRunner(
        [
            f"I will ask epistemic.\n{epi}",
            f"List the folder.\n{listed}",
            f"Read commands.py.\n{read}",
            answer,
        ]
    )
    agent = _ask_agent(
        runner,
        max_iterations=10,
        verification_root=tmp_path,
        codeintel_root=tmp_path,
    )
    result = agent.run("what command types does it have already and what args do they take")
    used = [tr.tool_name for step in result.steps for tr in step.tool_results]
    assert "ask_epistemic" not in used
    assert "research_codebase" not in used
    assert "read_file" in used or "list_dir" in used
    assert result.stop_reason == StopReason.COMPLETED
    final = result.final_answer or ""
    assert "{{" not in final
    assert "unused" not in final.lower()
    assert "list_dir" in final or "read_file" in final
