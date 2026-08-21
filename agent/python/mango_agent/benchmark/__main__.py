"""CLI: python -m mango_agent.benchmark"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mango_agent.benchmark.accounting import AccountingModelRunner
from mango_agent.benchmark.runner import run_benchmark
from mango_agent.benchmark.tasks import TASKS
from mango_agent.types import AgentLimits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Mango coding benchmark through the full agent loop."
    )
    parser.add_argument("--tasks", help="Comma-separated task ids (default: all)")
    parser.add_argument("--list", action="store_true", help="Print task ids and exit")
    parser.add_argument(
        "--output-dir",
        default=str(Path("benchmark_reports")),
        help="Directory for JSON and Markdown reports",
    )
    parser.add_argument("--work-root", help="Parent directory for per-task workspaces")
    parser.add_argument("--config", help="Path to runtime config.yaml")
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--max-runtime-seconds", type=float, default=240)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument(
        "--thought-max-tokens",
        type=int,
        default=512,
        help="Unconstrained thought tokens before the tool-call trigger (GBNF mode).",
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument(
        "--top-p",
        type=float,
        default=0.95,
        dest="top_p",
        help="Nucleus sampling; keep near 0.95–1.0 when temperature is low.",
    )
    parser.add_argument(
        "--grammar",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-grammar",
        action="store_true",
        help="Disable GBNF tool-call grammar (debug). Default is lazy GBNF while tests are red.",
    )
    args = parser.parse_args(argv)

    if args.list:
        print(f"{'id':<28} {'cat':<12} {'diff':<8} title")
        for task in TASKS:
            print(f"{task.id:<28} {task.category:<12} {task.difficulty:<8} {task.title}")
        easy = sum(1 for task in TASKS if task.difficulty == "easy")
        medium = sum(1 for task in TASKS if task.difficulty == "medium")
        hard = sum(1 for task in TASKS if task.difficulty == "hard")
        print(f"# {len(TASKS)} tasks ({easy} easy / {medium} medium / {hard} hard)")
        return 0

    task_ids = [item.strip() for item in args.tasks.split(",") if item.strip()] if args.tasks else None
    from mango_runtime import ModelRunner

    inner = ModelRunner(args.config)
    inner.load()
    runner = AccountingModelRunner(inner)
    try:
        payload = run_benchmark(
            runner,
            task_ids=task_ids,
            work_root=Path(args.work_root) if args.work_root else None,
            output_dir=Path(args.output_dir),
            limits=AgentLimits(
                max_iterations=args.max_iterations,
                max_runtime_seconds=args.max_runtime_seconds,
                max_prompt_chars=48_000,
            ),
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            use_tool_grammar=not args.no_grammar,
            thought_max_tokens=args.thought_max_tokens,
        )
    finally:
        runner.close()

    print(
        f"[Mango bench] {payload['passed']}/{payload['task_count']} passed "
        f"({payload['pass_rate'] * 100:.1f}%) tokens={payload['total_tokens']} "
        f"time={payload['total_elapsed_seconds']}s",
        flush=True,
    )
    print(f"[Mango bench] reports in {Path(args.output_dir).resolve()}", flush=True)
    return 0 if payload["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
