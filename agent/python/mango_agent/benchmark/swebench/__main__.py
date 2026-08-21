"""CLI: python -m mango_agent.benchmark.swebench"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mango_agent.benchmark.accounting import AccountingModelRunner
from mango_agent.benchmark.swebench.baseline import (
    compare_reports,
    load_baseline_config,
    render_comparison,
)
from mango_agent.benchmark.swebench.evaluate import run_official_evaluation
from mango_agent.benchmark.swebench.instances import (
    DEFAULT_DATASET,
    DEFAULT_SPLIT,
    LITE_DATASET_HF,
    load_instances,
    lite_instance_count,
)
from mango_agent.benchmark.swebench.runner import run_swebench
from mango_agent.types import AgentLimits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Mango on official SWE-bench Lite instances and evaluate with the Docker harness."
        )
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=(
            f"Official SWE-bench dataset alias or HF id (default: {DEFAULT_DATASET} -> "
            f"{LITE_DATASET_HF}, 300 test instances)"
        ),
    )
    parser.add_argument("--split", default=DEFAULT_SPLIT, help="Dataset split (test or dev)")
    parser.add_argument("--fixture", help="Optional local .json instance list (official schema)")
    parser.add_argument("--instances", help="Comma-separated official instance ids")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Run the curated 10-instance SWE-bench Lite baseline set",
    )
    parser.add_argument(
        "--baseline-config",
        help="Path to baseline JSON (default: bundled swebench-lite-baseline-10)",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of instances to run")
    parser.add_argument("--list", action="store_true", help="List instances and exit")
    parser.add_argument(
        "--output-dir",
        default=str(Path("swebench_reports")),
        help="Directory for JSON and Markdown reports",
    )
    parser.add_argument("--work-root", help="Parent directory for per-instance workspaces")
    parser.add_argument("--cache-root", help="Directory for cached GitHub clones")
    parser.add_argument("--predictions", help="Path for SWE-bench predictions JSON/JSONL")
    parser.add_argument("--model-name", default="mango-local", help="Label stored in predictions")
    parser.add_argument("--config", help="Path to runtime config.yaml")
    parser.add_argument("--max-iterations", type=int, default=30)
    parser.add_argument("--max-runtime-seconds", type=float, default=1200)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--thought-max-tokens", type=int, default=768)
    parser.add_argument("--tool-max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=0.95, dest="top_p")
    parser.add_argument("--no-grammar", action="store_true", help="Disable GBNF tool-call grammar")
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run the official SWE-bench Docker harness after generating predictions",
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Skip agent inference; only run the official harness on --predictions",
    )
    parser.add_argument("--eval-run-id", help="Run id passed to the SWE-bench harness")
    parser.add_argument("--eval-workers", type=int, default=1, help="Parallel Docker workers for harness")
    parser.add_argument(
        "--compare",
        help="Compare this run against a reference report JSON (e.g. swebench_reports/baseline/reference.json)",
    )
    parser.add_argument(
        "--save-reference",
        action="store_true",
        help="After the run, save latest.json as reference.json in --output-dir",
    )
    args = parser.parse_args(argv)

    baseline_config: dict | None = None
    if args.baseline or args.baseline_config:
        baseline_config = load_baseline_config(
            Path(args.baseline_config) if args.baseline_config else None
        )
        if args.baseline:
            args.dataset = str(baseline_config.get("dataset") or DEFAULT_DATASET)
            args.split = str(baseline_config.get("split") or DEFAULT_SPLIT)

    instance_ids = [item.strip() for item in args.instances.split(",") if item.strip()] if args.instances else None
    if baseline_config and not instance_ids:
        instance_ids = [str(item) for item in baseline_config["instance_ids"]]
    fixture_path = Path(args.fixture) if args.fixture else None

    if args.list:
        items = load_instances(
            dataset_name=args.dataset,
            split=args.split,
            fixture_path=fixture_path,
            instance_ids=instance_ids,
            limit=args.limit,
        )
        print(f"{'instance_id':<34} repo")
        for item in items:
            print(f"{item.instance_id:<34} {item.repo}")
        if baseline_config:
            print(f"# baseline {baseline_config.get('name')} ({len(items)} instances)")
        else:
            total = (
                lite_instance_count(args.split)
                if args.dataset in {DEFAULT_DATASET, "lite", LITE_DATASET_HF}
                else len(items)
            )
            print(f"# {len(items)} listed / {total} in dataset ({args.dataset}, split={args.split})")
        return 0

    if args.evaluate_only:
        if not args.predictions:
            print("--evaluate-only requires --predictions", file=sys.stderr)
            return 2
        run_id = args.eval_run_id or f"mango-{int(__import__('time').time())}"
        summary = run_official_evaluation(
            predictions_path=Path(args.predictions),
            dataset_name=args.dataset,
            split=args.split,
            run_id=run_id,
            model_name=args.model_name,
            max_workers=args.eval_workers,
            instance_ids=instance_ids,
            report_dir=Path(args.output_dir),
        )
        print(
            f"[Mango SWE-bench] resolved {summary['resolved_count']}/{summary['total']} "
            f"({float(summary.get('pass_rate') or 0) * 100:.1f}%)",
            flush=True,
        )
        return 0 if summary.get("resolved_count") == summary.get("total") and summary.get("total") else 1

    from mango_runtime import ModelRunner

    inner = ModelRunner(args.config)
    inner.load()
    runner = AccountingModelRunner(inner)
    output_dir = Path(args.output_dir)
    try:
        payload = run_swebench(
            runner,
            dataset_name=args.dataset,
            split=args.split,
            fixture_path=fixture_path,
            instance_ids=instance_ids,
            limit=args.limit,
            work_root=Path(args.work_root) if args.work_root else None,
            cache_root=Path(args.cache_root) if args.cache_root else None,
            output_dir=output_dir,
            predictions_path=Path(args.predictions) if args.predictions else None,
            model_name=args.model_name,
            limits=AgentLimits(
                max_iterations=args.max_iterations,
                max_runtime_seconds=args.max_runtime_seconds,
                max_prompt_chars=96_000,
            ),
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            use_tool_grammar=not args.no_grammar,
            thought_max_tokens=args.thought_max_tokens,
            tool_max_tokens=args.tool_max_tokens,
            evaluate=args.evaluate,
            eval_run_id=args.eval_run_id,
            eval_max_workers=args.eval_workers,
        )
    finally:
        runner.close()

    if baseline_config:
        payload["baseline_name"] = baseline_config.get("name")

    if args.save_reference:
        latest = output_dir / "latest.json"
        reference = output_dir / "reference.json"
        reference.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[Mango SWE-bench] saved reference -> {reference.resolve()}", flush=True)

    if args.compare:
        reference = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        comparison = compare_reports(payload, reference)
        comparison["task_count"] = payload.get("task_count")
        text = render_comparison(comparison)
        print(text, flush=True)
        (output_dir / "comparison.md").write_text(text, encoding="utf-8")
        (output_dir / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    patch_rate = float(payload.get("patch_rate") or 0) * 100
    print(
        f"[Mango SWE-bench] patches {payload['patch_count']}/{payload['task_count']} "
        f"({patch_rate:.1f}%) tokens={payload['total_tokens']} time={payload['total_elapsed_seconds']}s",
        flush=True,
    )
    if payload.get("pass_rate") is not None:
        print(
            f"[Mango SWE-bench] resolved {payload['resolved']}/{payload['task_count']} "
            f"({float(payload['pass_rate']) * 100:.1f}%)",
            flush=True,
        )
    print(f"[Mango SWE-bench] predictions: {payload['predictions_path']}", flush=True)
    print(f"[Mango SWE-bench] reports in {output_dir.resolve()}", flush=True)
    if args.evaluate and payload.get("pass_rate") is None:
        print("[Mango SWE-bench] harness evaluation did not produce resolved scores.", file=sys.stderr)
    if args.evaluate:
        failed = payload["task_count"] - (payload["resolved"] or 0)
        return 0 if failed == 0 and payload["task_count"] > 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
