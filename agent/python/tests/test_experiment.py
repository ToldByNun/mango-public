from __future__ import annotations

import json
from pathlib import Path

from mango_agent.experiment import (
    decide_experiment,
    goal_wants_perf,
    restore_snapshots,
    speed_delta_pct,
)
from test_agent_loop import FakeModelRunner
from mango_agent import Agent, StopReason
from mango_tools import create_default_registry


def test_perf_regression_reverts() -> None:
    verdict = decide_experiment(
        syntax_ok=True,
        tests_ok=True,
        before_ms=1.82,
        after_ms=1.91,
        hypothesis="this should be faster",
    )
    assert verdict.decision == "revert"
    assert verdict.reason == "regression"
    assert verdict.delta_pct == speed_delta_pct(1.82, 1.91)
    assert verdict.delta_pct == -4.9


def test_perf_improvement_keeps() -> None:
    verdict = decide_experiment(
        syntax_ok=True,
        tests_ok=True,
        before_ms=1.82,
        after_ms=1.45,
        hypothesis="cache the hot path",
    )
    assert verdict.decision == "keep"
    assert verdict.reason == "keep"
    assert verdict.unsupported is False
    assert verdict.delta_pct == speed_delta_pct(1.82, 1.45)


def test_missed_speedup_claim_keeps_unsupported() -> None:
    verdict = decide_experiment(
        syntax_ok=True,
        tests_ok=True,
        before_ms=100.0,
        after_ms=98.0,
        claimed_speedup_pct=20.0,
        hypothesis="20% faster lookup",
    )
    assert verdict.decision == "keep"
    assert verdict.unsupported is True
    assert verdict.reason == "unsupported"
    assert verdict.delta_pct == 2.0


def test_restore_snapshots_writes_previous_bytes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    original = "def add(a, b):\n    return a + b\n"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    restored = restore_snapshots({str(target): original})
    assert restored == [str(target)]
    assert target.read_text(encoding="utf-8") == original


def test_restore_snapshots_skips_new_files(tmp_path: Path) -> None:
    target = tmp_path / "fresh.py"
    target.write_text("print(1)\n", encoding="utf-8")
    restored = restore_snapshots({str(target): ""})
    assert restored == []
    assert target.read_text(encoding="utf-8") == "print(1)\n"


def test_failing_pytest_restores_snapshot(tmp_path: Path) -> None:
    original = "def add(a, b):\n    return a + b\n"
    (tmp_path / "app.py").write_text(original, encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(1, 1) == 2\n",
        encoding="utf-8",
    )
    bad = "def add(a, b):\n    return a - b\n"
    read = f'<tool_call=read_file : {json.dumps({"path": "app.py"})}>'
    write = f'<tool_call=write_file : {json.dumps({"path": "app.py", "content": bad})}>'
    runner = FakeModelRunner([read, write, "I will try a different change.", "still working"])
    seen: list[dict] = []
    agent = Agent(
        runner,
        max_iterations=4,
        require_tools=True,
        task_wants_tests=True,
        plan_apis_first=False,
        codeintel_root=tmp_path,
        verification_root=tmp_path,
        tool_registry=create_default_registry(),
        on_event=lambda event: seen.append(event),
    )
    result = agent.run("Fix add() so the tests pass")
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == original
    names = [item["event"] for item in seen]
    assert "agent.experiment" in names
    experiment = next(item for item in seen if item["event"] == "agent.experiment")
    assert experiment["payload"]["decision"] == "revert"
    assert experiment["payload"]["reason"] == "tests_failed"
    assert result.stop_reason in {StopReason.COMPLETED, StopReason.MAX_ITERATIONS, StopReason.ERROR}


def test_goal_wants_perf_keywords() -> None:
    assert goal_wants_perf("Make clamp 20% faster")
    assert goal_wants_perf("Bitte schneller machen")
    assert not goal_wants_perf("Add a README")
