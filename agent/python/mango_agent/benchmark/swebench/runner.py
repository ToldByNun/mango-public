"""Run Mango on SWE-bench instances and collect patches."""

from __future__ import annotations

import time
import warnings
from pathlib import Path
from typing import Any

from mango_agent.benchmark.accounting import AccountingModelRunner
from mango_agent.benchmark.swebench.instances import DEFAULT_DATASET, SweBenchInstance, load_instances
from mango_agent.benchmark.swebench.predictions import write_predictions
from mango_agent.benchmark.swebench.report import write_swebench_reports
from mango_agent.benchmark.swebench.types import SweBenchOutcome
from mango_agent.benchmark.swebench.workspace import (
    SWE_BENCH_DISABLED_TOOLS,
    SWE_BENCH_SYSTEM_PROMPT,
    build_goal,
    cleanup_instance_workspace,
    collect_model_patch,
    prepare_instance_workspace,
)
from mango_agent.orchestrator import Orchestrator
from mango_agent.types import AgentLimits, AgentResult, StopReason


def run_instance(
    instance: SweBenchInstance,
    root: Path,
    model_runner: Any,
    *,
    cache_root: Path | None = None,
    limits: AgentLimits | None = None,
    max_tokens: int | None = 4096,
    temperature: float | None = 0.1,
    top_p: float | None = 0.95,
    use_tool_grammar: bool = True,
    thought_max_tokens: int | None = 768,
    tool_max_tokens: int | None = 2048,
    verbose: bool = True,
) -> SweBenchOutcome:
    prepare_instance_workspace(instance, root, cache_root=cache_root)
    goal = build_goal(instance)
    inner = model_runner
    while isinstance(inner, AccountingModelRunner):
        inner = inner.inner
    accounting = AccountingModelRunner(inner)
    started = time.monotonic()
    agent_result: AgentResult | None = None
    error: str | None = None
    orch: Orchestrator | None = None
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
            tool_max_tokens=tool_max_tokens,
            require_tools=True,
            task_wants_tests=True,
            verbose=verbose,
            disabled_tools=SWE_BENCH_DISABLED_TOOLS,
            system_prompt=SWE_BENCH_SYSTEM_PROMPT,
        )
        agent_result = orch.run(goal)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    finally:
        if orch is not None:
            orch.agent.close_index()
    elapsed = round(time.monotonic() - started, 4)
    patch = collect_model_patch(root)
    metrics = agent_result.metrics if agent_result is not None else None
    stop = agent_result.stop_reason.value if agent_result is not None else StopReason.ERROR.value
    iterations = agent_result.iterations if agent_result is not None else 0
    reasoning_cycles = metrics.reasoning_cycles if metrics else 0
    epistemic_calls = metrics.epistemic_calls if metrics else 0
    verify_runs = metrics.verification_runs if metrics else 0
    verify_fails = metrics.verification_failures if metrics else 0
    patch_ok = bool(patch.strip())
    tool_names = dict(metrics.tool_calls_by_name) if metrics else {}
    trace = []
    if agent_result is not None:
        for step in agent_result.steps:
            results_by_call = {
                id(result.call): result
                for result in step.tool_results
                if getattr(result, "call", None) is not None
            }
            tools = []
            for call in step.tool_calls:
                result = results_by_call.get(id(call))
                tools.append(
                    {
                        "name": call.name,
                        "ok": None if result is None else bool(result.success),
                        "error": None if result is None else result.error,
                    }
                )
            preview = ""
            if not step.tool_calls:
                preview = (step.model_output or "").replace("\n", " ").strip()[:240]
            trace.append(
                {
                    "iteration": step.iteration,
                    "reasoning_need": step.reasoning_need,
                    "reasoning_summary": step.reasoning_summary,
                    "tools": tools,
                    "output_preview": preview,
                }
            )
    failure_bucket = _classify_failure_bucket(agent_result, error=error, patch_ok=patch_ok)
    return SweBenchOutcome(
        instance_id=instance.instance_id,
        repo=instance.repo,
        success=error is None and patch_ok,
        resolved=None,
        model_patch=patch,
        patch_nonempty=patch_ok,
        stop_reason=stop,
        iterations=iterations,
        elapsed_seconds=metrics.elapsed_seconds if metrics else elapsed,
        prompt_tokens=accounting.prompt_tokens,
        completion_tokens=accounting.completion_tokens,
        total_tokens=accounting.total_tokens,
        tokens_estimated=accounting.estimated,
        model_complete_calls=accounting.complete_calls,
        reasoning_cycles=reasoning_cycles,
        epistemic_calls=epistemic_calls,
        verification_runs=verify_runs,
        verification_failures=verify_fails,
        error=error or (agent_result.error if agent_result else None),
        tool_calls_by_name=tool_names,
        extra={"trace": trace, "failure_bucket": failure_bucket},
    )


def run_swebench(
    model_runner: Any,
    *,
    dataset_name: str = DEFAULT_DATASET,
    split: str = "test",
    fixture_path: Path | None = None,
    instance_ids: list[str] | None = None,
    limit: int | None = None,
    count: int | None = None,
    shuffle: bool = False,
    shuffle_reset: bool = False,
    shuffle_seed: int | None = None,
    work_root: Path | None = None,
    cache_root: Path | None = None,
    output_dir: Path | None = None,
    predictions_path: Path | None = None,
    model_name: str = "mango-local",
    limits: AgentLimits | None = None,
    max_tokens: int | None = 4096,
    temperature: float | None = 0.1,
    top_p: float | None = 0.95,
    use_tool_grammar: bool = True,
    thought_max_tokens: int | None = 768,
    tool_max_tokens: int | None = 2048,
    evaluate: bool = False,
    eval_run_id: str | None = None,
    eval_max_workers: int = 1,
    verbose: bool = True,
) -> dict[str, Any]:
    warnings.filterwarnings("ignore", category=SyntaxWarning)
    run_count = count if count is not None else limit
    pool = load_instances(
        dataset_name=dataset_name,
        split=split,
        fixture_path=fixture_path,
        instance_ids=instance_ids,
        limit=None,
    )
    shuffle_state: dict[str, Any] | None = None
    if shuffle:
        from mango_agent.benchmark.swebench.shuffle import pick_shuffled_instances, shuffle_state_path

        if run_count is None:
            run_count = 1
        state_path = shuffle_state_path(Path(output_dir) if output_dir else Path.cwd() / "swebench_reports")
        instances, shuffle_state = pick_shuffled_instances(
            pool,
            count=run_count,
            state_path=state_path,
            dataset_name=dataset_name,
            split=split,
            seed=shuffle_seed,
            reset=shuffle_reset,
        )
        status = shuffle_state.get("remaining") or []
        print(
            f"[Mango SWE-bench] shuffle cycle={shuffle_state.get('cycle')} "
            f"picked={len(instances)} remaining_in_cycle={len(status)}",
            flush=True,
        )
    else:
        instances = pool[:run_count] if run_count is not None else pool
    base = work_root or (Path.cwd() / ".mango" / "swebench_runs")
    base.mkdir(parents=True, exist_ok=True)
    cache = cache_root or (Path.cwd() / ".mango" / "swebench" / "repo_cache")
    pred_path = predictions_path or (base / "predictions.json")
    outcomes: list[SweBenchOutcome] = []
    for index, instance in enumerate(instances, start=1):
        root = base / instance.instance_id
        cleanup_instance_workspace(instance, root, cache_root=cache)
        print(
            f"[Mango SWE-bench] start {index}/{len(instances)} "
            f"{instance.instance_id} ({instance.repo})",
            flush=True,
        )
        try:
            outcome = run_instance(
                instance,
                root,
                model_runner,
                cache_root=cache,
                limits=limits,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                use_tool_grammar=use_tool_grammar,
                thought_max_tokens=thought_max_tokens,
                tool_max_tokens=tool_max_tokens,
                verbose=verbose,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[Mango SWE-bench] ERROR {instance.instance_id}: {exc}", flush=True)
            outcome = SweBenchOutcome(
                instance_id=instance.instance_id,
                repo=instance.repo,
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
                reasoning_cycles=0,
                epistemic_calls=0,
                verification_runs=0,
                verification_failures=0,
                error=str(exc),
                extra={"failure_bucket": "runtime_error"},
            )
        outcomes.append(outcome)
        flag = "PATCH" if outcome.patch_nonempty else "EMPTY"
        tools = (
            ",".join(f"{name}={count}" for name, count in sorted(outcome.tool_calls_by_name.items()))
            or "(none)"
        )
        print(
            f"[Mango SWE-bench] {flag} {instance.instance_id} "
            f"stop={outcome.stop_reason} tools={tools} "
            f"iters={outcome.iterations} tokens={outcome.total_tokens} "
            f"{outcome.elapsed_seconds:.2f}s",
            flush=True,
        )
        if outcome.error:
            print(f"[Mango SWE-bench] error {instance.instance_id}: {outcome.error}", flush=True)
        write_predictions(outcomes, pred_path, model_name=model_name)
        if output_dir is not None:
            checkpoint = build_suite_payload(
                outcomes,
                dataset_name=dataset_name,
                split=split,
                predictions_path=str(pred_path),
                harness_summary=None,
                model_name=model_name,
            )
            write_swebench_reports(checkpoint, Path(output_dir), stamped=False)

    harness_summary: dict[str, Any] | None = None
    if evaluate:
        from mango_agent.benchmark.swebench.evaluate import (
            EvaluationError,
            docker_daemon_ready,
            run_official_evaluation,
        )

        ready, docker_msg = docker_daemon_ready()
        if not ready:
            print(f"[Mango SWE-bench] SKIP harness evaluation: {docker_msg}", flush=True)
            harness_summary = {
                "skipped": True,
                "error": docker_msg,
                "resolved_count": 0,
                "total": 0,
                "pass_rate": 0.0,
                "instances": [],
            }
        else:
            try:
                harness_summary = run_official_evaluation(
                    predictions_path=pred_path,
                    dataset_name=dataset_name,
                    split=split,
                    run_id=eval_run_id or f"mango-{int(time.time())}",
                    model_name=model_name,
                    max_workers=eval_max_workers,
                    instance_ids=[item.instance_id for item in instances],
                    report_dir=Path(output_dir) if output_dir else None,
                )
            except EvaluationError as exc:
                print(f"[Mango SWE-bench] harness evaluation failed: {exc}", flush=True)
                harness_summary = {
                    "failed": True,
                    "error": str(exc),
                    "resolved_count": 0,
                    "total": 0,
                    "pass_rate": 0.0,
                    "instances": [],
                }
        if harness_summary and not harness_summary.get("skipped") and not harness_summary.get("failed"):
            resolved = {
                str(item["instance_id"]): bool(item.get("resolved"))
                for item in harness_summary.get("instances", [])
            }
            for outcome in outcomes:
                if outcome.instance_id in resolved:
                    outcome.resolved = resolved[outcome.instance_id]
                    outcome.harness_report = next(
                        (
                            row
                            for row in harness_summary.get("instances", [])
                            if str(row.get("instance_id")) == outcome.instance_id
                        ),
                        None,
                    )
            for outcome in outcomes:
                outcome.success = bool(outcome.resolved)

    payload = build_suite_payload(
        outcomes,
        dataset_name=dataset_name,
        split=split,
        predictions_path=str(pred_path),
        harness_summary=harness_summary,
        model_name=model_name,
    )
    if shuffle_state is not None:
        payload["shuffle"] = {
            "cycle": shuffle_state.get("cycle"),
            "remaining_in_cycle": len(shuffle_state.get("remaining") or []),
            "completed_this_cycle": len(shuffle_state.get("completed") or []),
        }
    if output_dir is not None:
        write_swebench_reports(payload, Path(output_dir))
    return payload


def build_suite_payload(
    outcomes: list[SweBenchOutcome],
    *,
    dataset_name: str,
    split: str,
    predictions_path: str,
    harness_summary: dict[str, Any] | None,
    model_name: str,
) -> dict[str, Any]:
    patch_count = sum(1 for item in outcomes if item.patch_nonempty)
    resolved_count = sum(1 for item in outcomes if item.resolved is True)
    evaluated = any(item.resolved is not None for item in outcomes)
    total_tokens = sum(item.total_tokens for item in outcomes)
    total_seconds = sum(item.elapsed_seconds for item in outcomes)
    total_reasoning_cycles = sum(item.reasoning_cycles for item in outcomes)
    failure_buckets: dict[str, int] = {}
    for item in outcomes:
        bucket = str((item.extra or {}).get("failure_bucket") or ("patched" if item.patch_nonempty else "unknown"))
        failure_buckets[bucket] = failure_buckets.get(bucket, 0) + 1
    return {
        "suite": "swebench",
        "dataset_name": dataset_name,
        "split": split,
        "model_name": model_name,
        "task_count": len(outcomes),
        "patch_count": patch_count,
        "resolved": resolved_count if evaluated else None,
        "pass_rate": (
            round(resolved_count / len(outcomes), 4)
            if evaluated and outcomes
            else None
        ),
        "patch_rate": round(patch_count / len(outcomes), 4) if outcomes else 0.0,
        "total_tokens": total_tokens,
        "total_reasoning_cycles": total_reasoning_cycles,
        "total_elapsed_seconds": round(total_seconds, 4),
        "failure_buckets": failure_buckets,
        "predictions_path": predictions_path,
        "harness_summary": harness_summary,
        "instances": [item.to_dict() for item in outcomes],
    }


def _classify_failure_bucket(
    agent_result: AgentResult | None,
    *,
    error: str | None,
    patch_ok: bool,
) -> str:
    if error:
        return "runtime_error"
    if patch_ok:
        return "patched"
    if agent_result is None:
        return "no_result"
    text = "\n".join(
        [
            str(agent_result.final_answer or ""),
            str(agent_result.error or ""),
            str(agent_result.verification_report or ""),
            *[str(step.model_output or "") for step in agent_result.steps[-3:]],
        ]
    ).lower()
    tool_names = {call.name for step in agent_result.steps for call in step.tool_calls}
    if "old_string not found" in text:
        return "bad_edit_anchor"
    if "do not edit yet" in text or ("search_code" in tool_names and "read_file" not in tool_names and "edit_file" not in tool_names):
        return "stalled_after_search"
    if "truncated or invalid" in text:
        return "tool_json_invalid"
    if "verification failed" in text or "tests still fail" in text:
        return "verification_failed"
    if not tool_names:
        return "no_tool_call"
    return "empty_other"
