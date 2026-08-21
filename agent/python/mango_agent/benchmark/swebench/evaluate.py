"""Optional wrapper around the official SWE-bench Docker evaluation harness."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mango_agent.benchmark.swebench.instances import DEFAULT_DATASET, DEFAULT_SPLIT, require_swebench


class EvaluationError(Exception):
    pass


def docker_available() -> bool:
    return shutil.which("docker") is not None


def swebench_installed() -> bool:
    try:
        import swebench  # noqa: F401

        return True
    except ImportError:
        return False


def run_official_evaluation(
    *,
    predictions_path: Path,
    dataset_name: str = DEFAULT_DATASET,
    split: str = DEFAULT_SPLIT,
    run_id: str,
    model_name: str,
    max_workers: int = 1,
    timeout: int | None = None,
    instance_ids: list[str] | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    require_swebench()
    if not docker_available():
        raise EvaluationError("Docker is required for SWE-bench evaluation but was not found on PATH.")

    cmd = [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--split",
        split,
        "--predictions_path",
        str(predictions_path),
        "--run_id",
        run_id,
        "--max_workers",
        str(max_workers),
    ]
    if timeout is not None:
        cmd.extend(["--timeout", str(timeout)])
    if instance_ids:
        cmd.extend(["--instance_ids", *instance_ids])
    if report_dir is not None:
        cmd.extend(["--report_dir", str(report_dir)])

    print(f"[Mango SWE-bench] running official harness: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.stdout.strip():
        print(proc.stdout, flush=True)
    if proc.stderr.strip():
        print(proc.stderr, flush=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise EvaluationError(f"SWE-bench harness failed ({proc.returncode}): {detail}")

    return read_harness_summary(run_id, model_name, report_dir=report_dir or Path("."))


def read_harness_summary(
    run_id: str,
    model_name: str,
    *,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    require_swebench()
    from swebench.harness.constants import LOG_REPORT, RUN_EVALUATION_LOG_DIR

    safe_model = model_name.replace("/", "__")
    base_report_dir = report_dir or Path(".")
    summary_path = base_report_dir / f"{safe_model}.{run_id}.json"
    summary: dict[str, Any] | None = None
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    instances: list[dict[str, Any]] = []
    log_root = RUN_EVALUATION_LOG_DIR / run_id / safe_model
    if log_root.is_dir():
        for instance_dir in sorted(log_root.iterdir()):
            if not instance_dir.is_dir():
                continue
            report_file = instance_dir / LOG_REPORT
            if not report_file.is_file():
                continue
            try:
                report = json.loads(report_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            instance_id = instance_dir.name
            resolved = bool(report.get(instance_id, {}).get("resolved"))
            instances.append({"instance_id": instance_id, "resolved": resolved, "report": report})

    resolved_count = sum(1 for item in instances if item.get("resolved"))
    total = len(instances)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "model_name": model_name,
        "summary_path": str(summary_path) if summary_path.is_file() else None,
        "log_root": str(log_root) if log_root.is_dir() else None,
        "instances": instances,
        "resolved_count": summary.get("resolved_instances", resolved_count) if summary else resolved_count,
        "total": summary.get("completed_instances", total) if summary else total,
    }
    completed = payload["total"] or 0
    resolved = payload["resolved_count"] or 0
    payload["pass_rate"] = round(resolved / completed, 4) if completed else 0.0
    if summary:
        payload["official_summary"] = summary
    return payload
