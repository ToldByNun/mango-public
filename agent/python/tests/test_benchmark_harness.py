from __future__ import annotations

import json
from pathlib import Path

from mango_agent.benchmark.report import render_markdown, write_reports
from mango_agent.benchmark.runner import build_suite_payload, evaluate_workspace, prepare_workspace, run_task
from mango_agent.benchmark.tasks import TASKS, get_task
from test_agent_loop import FakeModelRunner


def _tool(name: str, **arguments: object) -> str:
    return f"<tool_call={name} : {json.dumps(arguments)}>"


def test_benchmark_defines_fifteen_representative_tasks() -> None:
    ids = [task.id for task in TASKS]
    assert len(TASKS) == 15
    assert len(ids) == len(set(ids))
    categories = {task.category for task in TASKS}
    assert categories >= {"bugfix", "feature", "refactor", "api", "multi_step"}
    by_diff = {level: [task.id for task in TASKS if task.difficulty == level] for level in ("easy", "medium", "hard")}
    assert len(by_diff["easy"]) == 5
    assert len(by_diff["medium"]) == 5
    assert len(by_diff["hard"]) == 5
    diffs = [task.difficulty for task in TASKS]
    assert diffs == ["easy"] * 5 + ["medium"] * 5 + ["hard"] * 5
    assert "bugfix_syntax_then_unique" in ids
    assert "feature_clamp" in ids


def test_syntax_then_unique_stub_does_not_parse(tmp_path: Path) -> None:
    task = get_task("bugfix_syntax_then_unique")
    root = tmp_path / task.id
    root.mkdir()
    prepare_workspace(task, root)
    source = (root / "uniqueutil.py").read_text(encoding="utf-8")
    try:
        compile(source, "uniqueutil.py", "exec")
    except SyntaxError:
        return
    raise AssertionError("stub uniqueutil.py should not parse")


def test_all_task_stubs_fail_verification(tmp_path: Path) -> None:
    for task in TASKS:
        root = tmp_path / task.id
        root.mkdir()
        prepare_workspace(task, root)
        _ok, tests_ok, report, extras = evaluate_workspace(task, root)
        assert not tests_ok, f"{task.id} stubs already pass tests:\n{report}\nextras={extras}"


def test_harness_records_success_metrics_with_fake_runner(tmp_path: Path) -> None:
    task = get_task("feature_clamp")
    root = tmp_path / "clamp"
    impl = "def clamp(value, lo, hi):\n    return max(lo, min(hi, value))\n"
    runner = FakeModelRunner(
        [
            _tool("write_file", path=str(root / "mathutil.py"), content=impl),
            "Implemented clamp.",
        ]
    )
    outcome = run_task(task, root, runner)
    assert outcome.success is True
    assert outcome.verification_success is True
    assert outcome.verification_failures == 0
    assert outcome.verification_runs >= 1
    assert outcome.iterations >= 1
    assert outcome.total_tokens > 0
    assert outcome.used_fix_loop is False
    payload = build_suite_payload([outcome])
    assert payload["passed"] == 1
    assert payload["pass_rate"] == 1.0
    text = render_markdown(payload)
    assert "feature_clamp" in text
    assert "PASS" in text
    out = tmp_path / "reports"
    json_path, md_path = write_reports(payload, out)
    assert json_path.is_file()
    assert md_path.is_file()
    assert (out / "latest.json").is_file()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["tasks"][0]["id"] == "feature_clamp"
