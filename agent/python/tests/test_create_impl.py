"""Greenfield create/implement: write_file must land; plan gate must fail-open."""

from __future__ import annotations

import json
from pathlib import Path

from mango_agent import Agent, StopReason
from mango_agent.agent import _PLAN_GATE_FAIL_OPEN_TURNS
from mango_agent.coding_phase import CodingPhase
from mango_context import ContextEngine
from mango_tools import create_default_registry
from test_agent_loop import FakeModelRunner

CREATE_CLI_GOAL = (
    "Create a Python CLI that reads a CSV path from argparse and prints row counts."
)


def test_finish_blocked_until_create_mutates(tmp_path: Path) -> None:
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        plan_apis_first=False,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = CREATE_CLI_GOAL
    agent._cli_goal = True
    agent._greenfield_run = True
    agent._impl_mutated_once = False
    assert agent._create_impl_goal()
    assert agent._finish_allowed() is False


def test_generic_create_extend_forces_write_file(tmp_path: Path) -> None:
    """Non-Discord create goals must not sole-lock insert_lines (empty workspace loops)."""
    target = tmp_path / "cli.py"
    target.write_text(
        "import argparse\ndef main():\n    pass\n",
        encoding="utf-8",
    )
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        plan_apis_first=False,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = CREATE_CLI_GOAL
    agent._cli_goal = True
    agent._greenfield_run = False
    agent._acted_once = True
    engine = ContextEngine(goal=CREATE_CLI_GOAL)
    agent._context = engine
    agent._refresh_impl_completeness(engine)
    agent._apply_coding_phase_steering(engine)
    assert agent._create_impl_goal()
    assert not agent._inventory_cli_budget()
    phase = agent._resolve_coding_phase()
    assert phase in (CodingPhase.CODE_EXTEND, CodingPhase.CODE_COMPLETE, CodingPhase.CODE_REPAIR)
    assert agent._forced_tool_name() == "write_file"
    assert agent._apply_grammar_filters(list(agent._enabled_registry_names())) == ["write_file"]


def test_plan_gate_fail_open_after_gated_turns(tmp_path: Path) -> None:
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        # Default registry so ask_epistemic is registered (custom registry skips it).
    )
    agent._task = (
        "Create a Discord bot that forwards messages to LM Studio via requests."
    )
    agent._cli_goal = True
    agent._apis_declared_once = True
    agent._epistemic_once = False
    agent._declared_libraries = ["discord", "requests"]
    engine = ContextEngine(goal=agent._task)
    agent._context = engine
    assert agent._registry.has("ask_epistemic")
    assert agent._plan_gate_phase() == "epistemic"
    agent._metric_plan_gate_turns = _PLAN_GATE_FAIL_OPEN_TURNS
    agent._maybe_fail_open_plan_gate(engine)
    assert agent._plan_gate_phase() is None
    assert agent._prefer_write_file is True
    assert agent._forced_tool_name() == "write_file"


def test_create_run_writes_file_after_plan_fail_open(tmp_path: Path) -> None:
    """Fake model stuck in ask_epistemic until turn budget → still writes."""
    declare = '<tool_call=declare_apis : {"libraries": "requests"}>'
    ask = '<tool_call=ask_epistemic : {"question": "requests.get signature"}>'
    write = (
        "<tool_call=write_file : "
        + json.dumps(
            {
                "path": "fetch.py",
                "content": (
                    "import argparse\nimport requests\n\n"
                    "def main():\n"
                    "    p = argparse.ArgumentParser()\n"
                    "    p.add_argument('url')\n"
                    "    args = p.parse_args()\n"
                    "    print(requests.get(args.url, timeout=10).status_code)\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
            }
        )
        + ">"
    )

    def _ask(question: str, _context=None):
        return {
            "exists": False,
            "install_ok": False,
            "install_command": "pip install requests",
            "failed": ["requests"],
            "details": "import failed: No module named 'requests'",
            "error": "install failed",
        }

    registry = create_default_registry()
    registry.register(
        "ask_epistemic",
        _ask,
        description="lookup",
        parameters={
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    )
    # Enough ask turns to hit fail-open, then write.
    outs = [declare] + [ask] * (_PLAN_GATE_FAIL_OPEN_TURNS + 1) + [write, "done", "done"]
    runner = FakeModelRunner(outs)
    agent = Agent(
        runner,
        max_iterations=12,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=registry,
        use_tool_grammar=True,
    )
    result = agent.run(
        "Create a Python script using requests that fetches a URL from argparse and prints status"
    )
    assert (tmp_path / "fetch.py").is_file()
    assert agent._impl_mutated_once is True
    assert result.error is None or "fake outputs" in str(result.error).lower()
