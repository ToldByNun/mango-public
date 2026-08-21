"""Run Mango coding-benchmark tasks through the full agent loop."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mango_agent.benchmark.accounting import AccountingModelRunner
from mango_agent.benchmark.report import write_reports
from mango_agent.benchmark.tasks import TASKS, BenchTask, get_task
from mango_agent.orchestrator import Orchestrator
from mango_agent.types import AgentLimits, AgentResult, StopReason
from mango_verification import run_verification


@dataclass
class TaskOutcome:
    id: str
    title: str
    category: str
    difficulty: str
    success: bool
    stop_reason: str
    iterations: int
    elapsed_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tokens_estimated: bool
    model_complete_calls: int
    epistemic_calls: int
    epistemic_subagent_iterations: int
    verification_runs: int
    verification_failures: int
    used_epistemic: bool
    used_fix_loop: bool
    verification_success: bool
    extra_check_ok: bool
    error: str | None = None
    verification_report: str | None = None
    extra_check_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_verify_config(root: Path, *, timeout: int = 60) -> None:
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (root / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": timeout}}),
        encoding="utf-8",
    )


def prepare_workspace(task: BenchTask, root: Path) -> str:
    for relative, content in task.files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    write_verify_config(root)
    return task.render_goal(root)


def extra_checks(task: BenchTask, root: Path) -> list[str]:
    errors: list[str] = []
    for relative, needles in task.expect_in_files.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing file {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                errors.append(f"{relative} does not contain {needle!r}")
    return errors


def evaluate_workspace(task: BenchTask, root: Path) -> tuple[bool, bool, str, list[str]]:
    result = run_verification(root)
    report = result.compact_report()
    extras = extra_checks(task, root)
    tests_ok = bool(result.success)
    return tests_ok and not extras, tests_ok, report, extras


def run_task(
    task: BenchTask,
    root: Path,
    model_runner: Any,
    *,
    limits: AgentLimits | None = None,
    max_tokens: int | None = 2048,
    temperature: float | None = 0.1,
    top_p: float | None = 0.95,
    use_tool_grammar: bool = True,
    thought_max_tokens: int | None = 512,
) -> TaskOutcome:
    goal = prepare_workspace(task, root)
    inner = model_runner
    while isinstance(inner, AccountingModelRunner):
        inner = inner.inner
    accounting = AccountingModelRunner(inner)
    started = time.monotonic()
    agent_result: AgentResult | None = None
    error: str | None = None
    try:
        orch = Orchestrator(
            accounting,
            workspace=root,
            limits=limits or AgentLimits(),
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            use_tool_grammar=use_tool_grammar,
            thought_max_tokens=thought_max_tokens,
        )
        agent_result = orch.run(goal)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    elapsed = round(time.monotonic() - started, 4)

    verify_ok, tests_ok, report, extras = evaluate_workspace(task, root)
    metrics = agent_result.metrics if agent_result is not None else None
    stop = agent_result.stop_reason.value if agent_result is not None else StopReason.ERROR.value
    iterations = agent_result.iterations if agent_result is not None else 0
    epistemic_calls = metrics.epistemic_calls if metrics else 0
    verify_runs = metrics.verification_runs if metrics else 0
    verify_fails = metrics.verification_failures if metrics else 0
    success = verify_ok and error is None
    return TaskOutcome(
        id=task.id,
        title=task.title,
        category=task.category,
        difficulty=task.difficulty,
        success=success,
        stop_reason=stop,
        iterations=iterations,
        elapsed_seconds=metrics.elapsed_seconds if metrics else elapsed,
        prompt_tokens=accounting.prompt_tokens,
        completion_tokens=accounting.completion_tokens,
        total_tokens=accounting.total_tokens,
        tokens_estimated=accounting.estimated,
        model_complete_calls=accounting.complete_calls,
        epistemic_calls=epistemic_calls,
        epistemic_subagent_iterations=metrics.epistemic_subagent_iterations if metrics else 0,
        verification_runs=verify_runs,
        verification_failures=verify_fails,
        used_epistemic=epistemic_calls > 0,
        used_fix_loop=verify_fails > 0,
        verification_success=tests_ok,
        extra_check_ok=not extras,
        error=error or (agent_result.error if agent_result else None),
        verification_report=report,
        extra_check_errors=extras,
    )


def run_benchmark(
    model_runner: Any,
    *,
    task_ids: list[str] | None = None,
    work_root: Path | None = None,
    output_dir: Path | None = None,
    limits: AgentLimits | None = None,
    max_tokens: int | None = 2048,
    temperature: float | None = 0.1,
    top_p: float | None = 0.95,
    use_tool_grammar: bool = True,
    thought_max_tokens: int | None = 512,
) -> dict[str, Any]:
    selected = [get_task(task_id) for task_id in task_ids] if task_ids else list(TASKS)
    base = Path(work_root) if work_root else Path.cwd() / ".mango" / "benchmark_runs"
    base.mkdir(parents=True, exist_ok=True)
    outcomes: list[TaskOutcome] = []
    for task in selected:
        task_dir = base / task.id
        if task_dir.exists():
            _reset_dir(task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        print(f"[Mango bench] start {task.id} ({task.category}/{task.difficulty})", flush=True)
        outcome = run_task(
            task,
            task_dir,
            model_runner,
            limits=limits,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            use_tool_grammar=use_tool_grammar,
            thought_max_tokens=thought_max_tokens,
        )
        outcomes.append(outcome)
        flag = "PASS" if outcome.success else "FAIL"
        print(
            f"[Mango bench] {flag} {task.id} iters={outcome.iterations} "
            f"tokens={outcome.total_tokens} verify={outcome.verification_runs}/"
            f"{outcome.verification_failures} {outcome.elapsed_seconds:.2f}s",
            flush=True,
        )
    payload = build_suite_payload(outcomes)
    if output_dir is not None:
        write_reports(payload, Path(output_dir))
    return payload


def build_suite_payload(outcomes: list[TaskOutcome]) -> dict[str, Any]:
    passed = sum(1 for item in outcomes if item.success)
    failed = len(outcomes) - passed
    total_tokens = sum(item.total_tokens for item in outcomes)
    total_seconds = sum(item.elapsed_seconds for item in outcomes)
    return {
        "suite": "mango-coding-benchmark",
        "task_count": len(outcomes),
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / len(outcomes), 4) if outcomes else 0.0,
        "total_tokens": total_tokens,
        "total_elapsed_seconds": round(total_seconds, 4),
        "used_epistemic_tasks": sum(1 for item in outcomes if item.used_epistemic),
        "used_fix_loop_tasks": sum(1 for item in outcomes if item.used_fix_loop),
        "tasks": [item.to_dict() for item in outcomes],
    }


def _reset_dir(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            _reset_dir(child)
            child.rmdir()
        else:
            child.unlink()
