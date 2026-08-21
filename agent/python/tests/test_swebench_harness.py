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
from mango_agent.benchmark.swebench.evaluate import docker_available, swebench_installed
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
from mango_agent.benchmark.swebench.workspace import build_goal, collect_model_patch, prepare_instance_workspace
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
    assert "mathutil.py" in outcome.model_patch
    assert outcome.tool_calls_by_name.get("edit_file", 0) >= 1
    logged = capsys.readouterr().err
    assert "tool=edit_file" in logged
    assert "iter 1/" in logged


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


@pytest.mark.swebench_live
def test_official_harness_requires_docker_and_predictions() -> None:
    if not swebench_installed():
        pytest.skip("swebench not installed")
    if not docker_available():
        from mango_agent.benchmark.swebench.evaluate import EvaluationError, run_official_evaluation

        with pytest.raises(EvaluationError, match="Docker"):
            run_official_evaluation(
                predictions_path=Path("missing.json"),
                dataset_name=DEFAULT_DATASET,
                run_id="mango-test",
                model_name="mango-test",
            )
