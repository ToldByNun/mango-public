"""Coding benchmark suite for the full Mango agent loop."""

from mango_agent.benchmark.runner import run_benchmark, run_task
from mango_agent.benchmark.tasks import TASKS, BenchTask, get_task, list_tasks

__all__ = [
    "TASKS",
    "BenchTask",
    "get_task",
    "list_tasks",
    "run_benchmark",
    "run_task",
]
