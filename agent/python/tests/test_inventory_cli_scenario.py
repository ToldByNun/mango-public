"""Scenario tests for the inventory CLI greenfield prompt (no real LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from mango_agent import Agent, StopReason
from mango_agent.impl_completeness import find_impl_gaps, required_features, summarize_impl_status
from mango_agent.work_plan import build_work_plan
from mango_tools import create_default_registry
from mango_tools.types import ToolCall
from test_agent_loop import FakeModelRunner

INVENTORY_GOAL = """\
schreib ein python projekt, das über die konsole läuft.
das projekt soll dafür da sein, bestehende items in meinem inventory zu tracken.
wir brauchen optionen um items hinzuzufügen, item count zu updaten, und items zu removen.
dazu auch item beschreibungen hinzufügen\
"""

PARTIAL_INVENTORY = """\
import argparse
import json
import os
from datetime import datetime

DB_FILE = "inventory.json"


def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": {}}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
"""


def test_work_plan_lists_inventory_features() -> None:
    plan = build_work_plan(INVENTORY_GOAL)
    assert "Work plan" in plan
    assert "read_file" in plan
    assert "add/create" in plan or "Implement:" in plan
    features = required_features(INVENTORY_GOAL)
    assert any("add" in f for f in features)
    assert any("remove" in f for f in features)
    assert any("update" in f for f in features)
    assert any("description" in f for f in features)


def test_impl_status_describes_content_not_bytes() -> None:
    status = summarize_impl_status(PARTIAL_INVENTORY, INVENTORY_GOAL, path="inventory.py")
    assert "lines of source" in status
    assert "399" not in status
    assert "load_db" in status
    assert "save_db" in status
    assert "MISSING" in status
    assert "add/create" in status or "Still missing" in status


def test_partial_inventory_has_feature_gaps() -> None:
    gaps = find_impl_gaps(PARTIAL_INVENTORY, INVENTORY_GOAL)
    assert any("__main__" in g for g in gaps)
    assert any("add" in g.lower() for g in gaps)


def test_type_command_blocked_use_read_file(tmp_path: Path) -> None:
    target = tmp_path / "inventory.py"
    target.write_text(PARTIAL_INVENTORY, encoding="utf-8")
    agent = Agent(
        FakeModelRunner(["x"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        tool_registry=create_default_registry(),
    )
    agent.run(INVENTORY_GOAL)
    call = ToolCall(
        name="run_terminal_command",
        arguments={"command": f"type {target}"},
        raw="",
        start=0,
        end=0,
    )
    reason = agent._grounding_block_reason(call)
    assert reason is not None
    assert "BLOCKED" in reason
    assert "read_file" in reason.lower()


def test_inventory_scenario_blocks_finish_and_keeps_plan_in_prompt(tmp_path: Path) -> None:
    target = tmp_path / "inventory.py"
    write = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": PARTIAL_INVENTORY})}>'
    )
    type_cmd = (
        f'<tool_call=run_terminal_command : {json.dumps({"command": f"type {target}"})}>'
    )
    done = "Das Projekt ist fertig – inventory.py ist vollständig."
    runner = FakeModelRunner([write, type_cmd, done])
    agent = Agent(
        runner,
        max_iterations=5,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    result = agent.run(INVENTORY_GOAL)
    assert result.stop_reason != StopReason.COMPLETED
    assert agent._impl_gaps
    assert any("Work plan" in p for p in runner.prompts)
    assert any("Implementation status" in p for p in runner.prompts)
    blocked = any(
        step.tool_results
        and not step.tool_results[0].success
        and step.tool_calls[0].name == "run_terminal_command"
        for step in result.steps
    )
    assert blocked
