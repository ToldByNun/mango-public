from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from mango_agent.benchmark.swebench.baseline import (
    baseline_instance_ids,
    compare_reports,
    load_baseline_config,
    render_comparison,
)
from mango_agent.benchmark.swebench.evaluate import (
    count_predictions,
    docker_available,
    docker_daemon_ready,
    merge_harness_into_report,
    swebench_installed,
)
from mango_agent.benchmark.swebench.shuffle import pick_shuffled_instances, shuffle_state_path, validate_count
from mango_agent.benchmark.swebench.instances import (
    DEFAULT_DATASET,
    LITE_DATASET_HF,
    SweBenchInstance,
    lite_instance_count,
    load_instances,
    require_swebench,
)
from mango_agent.benchmark.swebench.predictions import load_predictions, prediction_record, write_predictions
from mango_agent.benchmark.swebench.report import render_swebench_markdown, write_swebench_reports
from mango_agent.benchmark.swebench.runner import build_suite_payload, run_instance, run_swebench
from mango_agent.benchmark.swebench.types import SweBenchOutcome
from mango_agent.benchmark.swebench.workspace import (
    build_goal,
    collect_model_patch,
    prepare_instance_workspace,
    _normalize_patch_text,
)
from test_agent_loop import FakeModelRunner

FIXTURES = Path(__file__).parent / "fixtures"
LITE_SAMPLE = FIXTURES / "swebench_lite_sympy_20590.json"


def _tool(name: str, **arguments: object) -> str:
    return f"<tool_call={name} : {json.dumps(arguments)}>"


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(root: Path) -> str:
    _git(["init"], cwd=root)
    _git(["config", "user.email", "mango@test"], cwd=root)
    _git(["config", "user.name", "Mango"], cwd=root)
    (root / "mathutil.py").write_text(
        "def add(a, b):\n    return f'{a}{b}'\n",
        encoding="utf-8",
    )
    (root / "test_mathutil.py").write_text(
        "from mathutil import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    _git(["add", "."], cwd=root)
    _git(["commit", "-m", "broken add"], cwd=root)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return commit.stdout.strip()


@pytest.mark.skipif(not swebench_installed(), reason="swebench package not installed")
def test_official_lite_sample_fixture_matches_schema() -> None:
    require_swebench()
    assert LITE_SAMPLE.is_file(), "missing checked-in SWE-bench Lite sample fixture"
    raw = json.loads(LITE_SAMPLE.read_text(encoding="utf-8"))
    record = raw[0] if isinstance(raw, list) else raw
    instance = SweBenchInstance.from_official(record)
    assert instance.instance_id == "sympy__sympy-20590"
    assert instance.repo == "sympy/sympy"
    assert instance.base_commit
    assert instance.problem_statement
    assert instance.data.get("eval_script")
    assert instance.data.get("FAIL_TO_PASS")


@pytest.mark.skipif(not swebench_installed(), reason="swebench package not installed")
def test_load_instances_from_local_official_json() -> None:
    items = load_instances(
        dataset_name="unused",
        fixture_path=LITE_SAMPLE,
        instance_ids=["sympy__sympy-20590"],
    )
    assert len(items) == 1
    assert items[0].instance_id == "sympy__sympy-20590"


@pytest.mark.swebench_live
@pytest.mark.skipif(not swebench_installed(), reason="swebench package not installed")
def test_load_official_swebench_lite_from_hf() -> None:
    items = load_instances(
        dataset_name=DEFAULT_DATASET,
        split="test",
        instance_ids=["sympy__sympy-20590"],
    )
    assert len(items) == 1
    assert items[0].repo == "sympy/sympy"
    assert lite_instance_count("test") == 300


def test_build_goal_includes_problem_statement() -> None:
    instance = SweBenchInstance.from_official(
        {
            "instance_id": "x",
            "repo": "org/repo",
            "base_commit": "abc",
            "problem_statement": "Fix the crash in parser.",
            "hints_text": "Try input.py",
            "FAIL_TO_PASS": ["test_crash"],
        }
    )
    goal = build_goal(instance)
    assert "Fix the crash in parser." in goal
    assert "Hints:" in goal
    assert "input.py" in goal
    assert "Failing tests" in goal
    assert "test_crash" in goal
    assert "edit_file" in goal


def test_prepare_workspace_and_collect_patch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    commit = _init_repo(source)
    instance = SweBenchInstance(
        data={
            "instance_id": "local__demo",
            "repo": "mango/demo",
            "base_commit": commit,
            "problem_statement": "Fix add().",
        },
        local_repo_path=str(source),
    )
    workspace = tmp_path / "workspace"
    prepare_instance_workspace(instance, workspace)
    target = workspace / "mathutil.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    patch = collect_model_patch(workspace)
    assert "mathutil.py" in patch


def test_prepare_workspace_replaces_leftover_worktree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    commit = _init_repo(source)
    cache = tmp_path / "cache"
    cached = cache / "mango__demo"
    shutil.copytree(source, cached)
    dest = tmp_path / "runs" / "local__demo"
    instance = SweBenchInstance(
        data={
            "instance_id": "local__demo",
            "repo": "mango/demo",
            "base_commit": commit,
            "problem_statement": "Fix add().",
        }
    )
    from mango_agent.benchmark.swebench.workspace import clone_or_copy_repo

    clone_or_copy_repo(instance, dest, cache)
    junk = dest / "junk.txt"
    junk.write_text("stale", encoding="utf-8")
    os.chmod(junk, stat.S_IREAD)
    clone_or_copy_repo(instance, dest, cache)
    assert dest.is_dir()
    assert (dest / "mathutil.py").is_file()
    assert not junk.exists()


def test_prediction_format_matches_official_schema(tmp_path: Path) -> None:
    outcome = SweBenchOutcome(
        instance_id="sympy__sympy-20590",
        repo="sympy/sympy",
        success=True,
        resolved=None,
        model_patch="diff --git a/a.py b/a.py",
        patch_nonempty=True,
        stop_reason="done",
        iterations=3,
        elapsed_seconds=1.2,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        tokens_estimated=False,
        model_complete_calls=2,
        epistemic_calls=0,
        verification_runs=1,
        verification_failures=0,
    )
    record = prediction_record(outcome, model_name="mango-test")
    assert set(record) == {"instance_id", "model_patch", "model_name_or_path"}
    path = tmp_path / "preds.json"
    write_predictions([outcome], path, model_name="mango-test")
    loaded = load_predictions(path)
    assert loaded[0]["instance_id"] == "sympy__sympy-20590"


def _search_then_fix(workspace: Path) -> list[str]:
    return [
        _tool("search_code", pattern="def add"),
        _tool("read_file", path=str(workspace / "mathutil.py")),
        _tool(
            "edit_file",
            path=str(workspace / "mathutil.py"),
            old_string="return f'{a}{b}'",
            new_string="return a + b",
        ),
        "Fixed add().",
    ]


def test_run_instance_produces_patch_with_fake_runner(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    commit = _init_repo(source)
    instance = SweBenchInstance(
        data={
            "instance_id": "local__demo",
            "repo": "mango/demo",
            "base_commit": commit,
            "problem_statement": "Fix add().",
        },
        local_repo_path=str(source),
    )
    workspace = tmp_path / "run"
    runner = FakeModelRunner(_search_then_fix(workspace))
    outcome = run_instance(
        instance,
        workspace,
        runner,
        limits=__import__("mango_agent.types", fromlist=["AgentLimits"]).AgentLimits(max_iterations=6),
    )
    assert outcome.patch_nonempty is True
    assert outcome.success is True
    assert outcome.stop_reason == "completed"
    assert "mathutil.py" in outcome.model_patch
    assert outcome.tool_calls_by_name.get("edit_file", 0) >= 1
    assert outcome.tool_calls_by_name.get("run_tests", 0) == 0
    assert (outcome.extra or {}).get("patch_applies_cleanly") is True
    logged = capsys.readouterr().err
    assert "tool=edit_file" in logged
    assert "iter 1/" in logged


def test_run_instance_empty_patch_is_not_success(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    commit = _init_repo(source)
    instance = SweBenchInstance(
        data={
            "instance_id": "local__empty",
            "repo": "mango/demo",
            "base_commit": commit,
            "problem_statement": "Fix add().",
        },
        local_repo_path=str(source),
    )
    workspace = tmp_path / "run_empty"
    # Prose only — no tools, no diff.
    runner = FakeModelRunner(["I looked at the issue and it is already fine.", "done"])
    outcome = run_instance(
        instance,
        workspace,
        runner,
        limits=__import__("mango_agent.types", fromlist=["AgentLimits"]).AgentLimits(max_iterations=4),
    )
    assert outcome.patch_nonempty is False
    assert outcome.success is False
    assert "empty patch" in (outcome.error or "").lower() or outcome.stop_reason != "completed"


def test_build_goal_points_at_docker_not_local_pytest() -> None:
    instance = SweBenchInstance(
        data={
            "instance_id": "x",
            "repo": "a/b",
            "base_commit": "abc",
            "problem_statement": "Bug.",
            "FAIL_TO_PASS": '["test_foo"]',
        }
    )
    goal = build_goal(instance)
    assert "test_foo" in goal
    assert "Docker" in goal or "docker" in goal.lower() or "FAIL_TO_PASS" in goal or "stop" in goal.lower()
    assert "Re-run the relevant failing tests" not in goal


def test_collect_model_patch_normalizes_lf(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    _init_repo(source)
    target = source / "mathutil.py"
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("return f'{a}{b}'", "return a + b"), encoding="utf-8")
    patch = collect_model_patch(source)
    assert patch
    assert "\r" not in patch
    assert patch.endswith("\n")
    from mango_agent.benchmark.swebench.workspace import patch_applies_cleanly

    assert patch_applies_cleanly(source, patch) is True


def test_patch_mode_finish_after_edit_without_run_tests(tmp_path: Path) -> None:
    """Regression: task_wants_tests must not block SWE-bench finish after a good edit."""
    from mango_agent import Agent, StopReason
    from mango_agent.benchmark.swebench.workspace import SWE_BENCH_DISABLED_TOOLS
    from mango_tools import create_default_registry

    _init_repo(tmp_path)

    read = (
        '<tool_call=read_file : '
        + json.dumps({"path": "mathutil.py"})
        + ">"
    )
    edit = (
        '<tool_call=edit_file : '
        + json.dumps(
            {
                "path": "mathutil.py",
                "old_string": "return f'{a}{b}'",
                "new_string": "return a + b",
            }
        )
        + ">"
    )
    runner = FakeModelRunner([read, edit, "Fixed add()."])
    agent = Agent(
        runner,
        max_iterations=6,
        verification_root=tmp_path,
        codeintel_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        disabled_tools=SWE_BENCH_DISABLED_TOOLS,
        tool_registry=create_default_registry(),
        use_tool_grammar=True,
    )
    assert "write_file" in agent._disabled_tools
    result = agent.run(
        "Fix the following GitHub issue in this repository.\n\n"
        "add() concatenates instead of adding.\n\n"
        "Make the minimal code changes needed to resolve the issue."
    )
    assert agent._patch_repo_mode()
    assert agent._impl_mutated_once
    assert result.stop_reason == StopReason.COMPLETED
    assert "run_tests" not in {
        call.name for step in result.steps for call in step.tool_calls
    }


def test_run_swebench_with_local_fixture_and_fake_runner(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    commit = _init_repo(source)
    record = {
        "instance_id": "local__demo",
        "repo": "mango/demo",
        "base_commit": commit,
        "problem_statement": "Fix add().",
        "local_repo_path": str(source),
    }
    fixture = tmp_path / "instances.json"
    fixture.write_text(json.dumps([record]), encoding="utf-8")
    work_root = tmp_path / "swebench_runs"
    workspace = work_root / "local__demo"
    runner = FakeModelRunner(_search_then_fix(workspace))
    payload = run_swebench(
        runner,
        dataset_name="unused",
        fixture_path=fixture,
        work_root=work_root,
        output_dir=tmp_path / "reports",
        limits=__import__("mango_agent.types", fromlist=["AgentLimits"]).AgentLimits(max_iterations=6),
    )
    assert payload["dataset_name"] == "unused"
    assert payload["task_count"] == 1
    assert payload["patch_count"] == 1
    assert Path(payload["predictions_path"]).is_file()
    text = render_swebench_markdown(payload)
    assert "local__demo" in text
    json_path, md_path = write_swebench_reports(payload, tmp_path / "reports2")
    assert json_path.is_file()
    assert md_path.is_file()


def test_build_suite_payload_tracks_patch_rate() -> None:
    outcomes = [
        SweBenchOutcome(
            instance_id="sympy__sympy-20590",
            repo="sympy/sympy",
            success=True,
            resolved=None,
            model_patch="patch",
            patch_nonempty=True,
            stop_reason="done",
            iterations=1,
            elapsed_seconds=1.0,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            tokens_estimated=False,
            model_complete_calls=1,
            epistemic_calls=0,
            verification_runs=0,
            verification_failures=0,
        ),
        SweBenchOutcome(
            instance_id="django__django-1",
            repo="django/django",
            success=False,
            resolved=None,
            model_patch="",
            patch_nonempty=False,
            stop_reason="error",
            iterations=0,
            elapsed_seconds=0.0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            tokens_estimated=False,
            model_complete_calls=0,
            epistemic_calls=0,
            verification_runs=0,
            verification_failures=0,
        ),
    ]
    payload = build_suite_payload(
        outcomes,
        dataset_name=DEFAULT_DATASET,
        split="test",
        predictions_path="/tmp/p.json",
        harness_summary=None,
        model_name="mango-test",
    )
    assert payload["patch_count"] == 1
    assert payload["patch_rate"] == 0.5
    assert payload["dataset_name"] == DEFAULT_DATASET


def test_baseline_config_loads_ten_official_instances() -> None:
    config = load_baseline_config()
    assert config["name"] == "swebench-lite-baseline-10"
    ids = baseline_instance_ids()
    assert len(ids) == 10
    assert "sympy__sympy-20590" in ids
    assert "django__django-10914" in ids


def test_compare_reports_shows_regression() -> None:
    reference = {
        "suite": "swebench",
        "task_count": 2,
        "resolved": 1,
        "pass_rate": 0.5,
        "patch_rate": 1.0,
        "total_tokens": 100,
        "total_elapsed_seconds": 10.0,
        "instances": [
            {"instance_id": "a", "resolved": True, "patch_nonempty": True},
            {"instance_id": "b", "resolved": False, "patch_nonempty": True},
        ],
    }
    current = dict(reference)
    current["resolved"] = 2
    current["pass_rate"] = 1.0
    current["total_tokens"] = 80
    current["instances"] = [
        {"instance_id": "a", "resolved": True, "patch_nonempty": True},
        {"instance_id": "b", "resolved": True, "patch_nonempty": True},
    ]
    comparison = compare_reports(current, reference)
    assert comparison["pass_rate"]["delta"] == 0.5
    assert comparison["total_tokens"]["delta"] == -20
    text = render_comparison(comparison)
    assert "baseline comparison" in text.lower()


def test_evaluate_helpers_report_optional_deps() -> None:
    assert isinstance(swebench_installed(), bool)
    assert isinstance(docker_available(), bool)
    ready, msg = docker_daemon_ready()
    assert isinstance(ready, bool)
    assert isinstance(msg, str)


def test_count_predictions_json_and_jsonl(tmp_path: Path) -> None:
    json_path = tmp_path / "predictions.json"
    json_path.write_text(
        json.dumps(
            [
                {"instance_id": "a", "model_patch": "", "model_name_or_path": "m"},
                {"instance_id": "b", "model_patch": "x", "model_name_or_path": "m"},
            ]
        ),
        encoding="utf-8",
    )
    assert count_predictions(json_path) == 2
    assert count_predictions(json_path, nonempty_only=True) == 1
    jsonl = tmp_path / "predictions.jsonl"
    jsonl.write_text(
        '{"instance_id":"a"}\n{"instance_id":"b","model_patch":"diff"}\n',
        encoding="utf-8",
    )
    assert count_predictions(jsonl) == 2
    assert count_predictions(jsonl, nonempty_only=True) == 1


def test_merge_harness_into_report(tmp_path: Path) -> None:
    report = {
        "task_count": 2,
        "patch_count": 1,
        "resolved": None,
        "pass_rate": None,
        "instances": [
            {"instance_id": "a__1", "resolved": None, "success": False},
            {"instance_id": "b__2", "resolved": None, "success": False},
        ],
    }
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    merge_harness_into_report(
        path,
        {
            "run_id": "mango-test",
            "resolved_count": 1,
            "total": 2,
            "pass_rate": 0.5,
            "instances": [
                {"instance_id": "a__1", "resolved": True},
                {"instance_id": "b__2", "resolved": False},
            ],
        },
    )
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["resolved"] == 1
    assert updated["pass_rate"] == 0.5
    assert updated["instances"][0]["resolved"] is True
    assert updated["instances"][1]["resolved"] is False


def test_shuffle_deck_no_repeats_until_cycle_complete(tmp_path: Path) -> None:
    pool = [
        SweBenchInstance.from_official(
            {
                "instance_id": f"org__repo-{idx}",
                "repo": "org/repo",
                "base_commit": "abc",
                "problem_statement": f"issue {idx}",
            }
        )
        for idx in range(5)
    ]
    state_path = shuffle_state_path(tmp_path)
    first, s1 = pick_shuffled_instances(
        pool, count=2, state_path=state_path, dataset_name="lite", split="test", seed=1
    )
    second, s2 = pick_shuffled_instances(
        pool, count=2, state_path=state_path, dataset_name="lite", split="test", seed=1
    )
    assert len(first) == 2
    assert len(second) == 2
    assert len({item.instance_id for item in first + second}) == 4
    assert len(s2.get("remaining") or []) == 1


def test_shuffle_deck_reshuffles_after_full_cycle(tmp_path: Path) -> None:
    pool = [
        SweBenchInstance.from_official(
            {
                "instance_id": f"org__repo-{idx}",
                "repo": "org/repo",
                "base_commit": "abc",
                "problem_statement": f"issue {idx}",
            }
        )
        for idx in range(3)
    ]
    state_path = shuffle_state_path(tmp_path)
    ids: list[str] = []
    for _ in range(3):
        picked, _ = pick_shuffled_instances(
            pool, count=1, state_path=state_path, dataset_name="lite", split="test", seed=42
        )
        ids.append(picked[0].instance_id)
    assert len(set(ids)) == 3
    picked4, state = pick_shuffled_instances(
        pool, count=1, state_path=state_path, dataset_name="lite", split="test", seed=42
    )
    assert state.get("cycle") == 2
    assert len(picked4) == 1


def test_validate_count_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        validate_count(0, dataset_name=DEFAULT_DATASET, split="test")
    with pytest.raises(ValueError, match="<= 300"):
        validate_count(301, dataset_name=DEFAULT_DATASET, split="test")
    assert validate_count(10, dataset_name=DEFAULT_DATASET, split="test") == 10


def test_normalize_patch_text_forces_lf_and_stable_mode() -> None:
    raw = "diff --git a/x.py b/x.py\r\nindex abc..def 100755\r\nold mode 100755\r\nnew mode 100644\r\n"
    out = _normalize_patch_text(raw)
    assert "\r" not in out
    assert "index abc..def 100644" in out
    assert "old mode" not in out


def test_windows_harness_write_text_uses_lf(tmp_path: Path) -> None:
    from mango_agent.benchmark.swebench.harness_winfix import apply_windows_harness_fixes

    apply_windows_harness_fixes()
    patch = tmp_path / "patch.diff"
    patch.write_text("line1\nline2\n")
    assert b"\r" not in patch.read_bytes()
    script = tmp_path / "eval.sh"
    script.write_text("#!/bin/bash\nset -e\n")
    assert b"\r" not in script.read_bytes()


@pytest.mark.swebench_live
def test_official_harness_requires_docker_and_predictions() -> None:
    if not swebench_installed():
        pytest.skip("swebench not installed")
    ready, _ = docker_daemon_ready()
    if not ready:
        from mango_agent.benchmark.swebench.evaluate import EvaluationError, run_official_evaluation

        with pytest.raises(EvaluationError, match="Docker"):
            run_official_evaluation(
                predictions_path=Path("missing.json"),
                dataset_name=DEFAULT_DATASET,
                run_id="mango-test",
                model_name="mango-test",
            )
