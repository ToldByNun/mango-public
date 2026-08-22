from __future__ import annotations

from pathlib import Path

from mango_agent import Agent, StopReason
from mango_agent.impl_completeness import find_impl_gaps, goal_wants_runnable_script
from mango_tools import create_default_registry
from test_agent_loop import FakeModelRunner

STUB_INVENTORY = """\
# inventory.py
import argparse
import json
import os

DB_FILE = "inventory.json"


def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": {}}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def add_item(db, name, count=1, description=""):
    items = db["items"]
    #
"""


COMPLETE_CLI = STUB_INVENTORY.replace(
    '    items = db["items"]\n    #',
    """    items = db["items"]
    items[name] = {"count": count, "description": description}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add")
    args = parser.parse_args()
    db = load_db()
    if args.cmd == "add":
        add_item(db, "sample")
    save_db(db)


if __name__ == "__main__":
    main()
""",
)


def test_goal_wants_runnable_german_console_project() -> None:
    goal = "schreib ein python projekt, das über die konsole läuft"
    assert goal_wants_runnable_script(goal)


def test_stub_inventory_has_gaps() -> None:
    goal = "schreib ein python projekt, das über die konsole läuft"
    gaps = find_impl_gaps(STUB_INVENTORY, goal)
    assert any("add_item" in gap for gap in gaps)
    assert any("__main__" in gap for gap in gaps)


def test_complete_cli_has_no_gaps() -> None:
    goal = "schreib ein python projekt, das über die konsole läuft"
    gaps = find_impl_gaps(COMPLETE_CLI, goal)
    assert gaps == []


def test_agent_blocks_finish_on_incomplete_greenfield_cli(tmp_path: Path) -> None:
    import json

    target = tmp_path / "inventory.py"
    write = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": STUB_INVENTORY})}>'
    )
    runner = FakeModelRunner([write, "Fertig. Das CLI-Projekt ist implementiert."])
    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Schreib ein Python-Projekt, das über die Konsole läuft.")
    assert result.stop_reason != StopReason.COMPLETED
    assert agent._impl_gaps
