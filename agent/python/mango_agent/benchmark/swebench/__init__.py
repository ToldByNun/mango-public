"""SWE-bench integration: run Mango on real GitHub issues and score with the official harness."""

from mango_agent.benchmark.swebench.instances import (
    DEFAULT_DATASET,
    LITE_DATASET_HF,
    SweBenchInstance,
    load_instances,
)
from mango_agent.benchmark.swebench.types import SweBenchOutcome
from mango_agent.benchmark.swebench.runner import run_instance, run_swebench

__all__ = [
    "DEFAULT_DATASET",
    "LITE_DATASET_HF",
    "SweBenchInstance",
    "SweBenchOutcome",
    "load_instances",
    "run_instance",
    "run_swebench",
]
