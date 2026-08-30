"""Optional wrapper around the official SWE-bench Docker evaluation harness."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from mango_agent.benchmark.swebench.instances import DEFAULT_DATASET, DEFAULT_SPLIT, require_swebench


class EvaluationError(Exception):
    pass


def docker_available() -> bool:
    """True when the docker CLI exists (may still be unreachable)."""
    return shutil.which("docker") is not None


def docker_daemon_ready() -> tuple[bool, str]:
    """True when Docker Desktop / daemon responds to ``docker info``."""
    if not docker_available():
        return False, "Docker CLI not found on PATH. Install Docker Desktop + WSL2 (see agent/README.md)."
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Docker daemon not reachable: {exc}"
    if proc.returncode == 0:
        return True, ""
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    tail = detail[-1] if detail else "docker info failed"
    if "CreateFile" in tail or "cannot find the file" in tail.lower():
        return False, "Docker Desktop is not running. Start Docker Desktop, then re-run with --evaluate."
    return False, f"Docker daemon not ready: {tail}"


def swebench_installed() -> bool:
    try:
        import swebench  # noqa: F401

        return True
    except ImportError:
        return False


def count_predictions(predictions_path: Path, *, nonempty_only: bool = False) -> int:
    """How many prediction records are in a JSON / JSONL predictions file."""
    path = Path(predictions_path)
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return 0

    def _count_records(records: list[Any]) -> int:
        if not nonempty_only:
            return len(records)
        n = 0
        for item in records:
            if not isinstance(item, dict):
                continue
            patch = str(item.get("model_patch") or item.get("patch") or "")
            if patch.strip():
                n += 1
        return n

    if path.suffix == ".jsonl" or text[:1] != "[":
        records: list[Any] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"model_patch": line})
        return _count_records(records)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return 0
    if isinstance(data, list):
        return _count_records(data)
    if isinstance(data, dict):
        # Either a single record or id -> record map.
        if "instance_id" in data or "model_patch" in data:
            return _count_records([data])
        return _count_records([v for v in data.values() if isinstance(v, dict)])
    return 0


def _eval_log_root(run_id: str, model_name: str) -> Path:
    from swebench.harness.constants import RUN_EVALUATION_LOG_DIR

    safe_model = model_name.replace("/", "__")
    return Path(RUN_EVALUATION_LOG_DIR) / run_id / safe_model


def scan_eval_progress(run_id: str, model_name: str) -> dict[str, Any]:
    """Scan harness log dirs for finished instance reports (safe to call mid-run)."""
    require_swebench()
    from swebench.harness.constants import LOG_REPORT

    log_root = _eval_log_root(run_id, model_name)
    instances: list[dict[str, Any]] = []
    if log_root.is_dir():
        for instance_dir in sorted(log_root.iterdir()):
            if not instance_dir.is_dir():
                continue
            report_file = instance_dir / LOG_REPORT
            if not report_file.is_file():
                continue
            try:
                report = json.loads(report_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            instance_id = instance_dir.name
            detail = report.get(instance_id) if isinstance(report, dict) else None
            if not isinstance(detail, dict):
                detail = {}
            resolved = bool(detail.get("resolved"))
            applied = bool(detail.get("patch_successfully_applied"))
            infra = bool(detail.get("infra_failure"))
            if resolved:
                status = "RESOLVED"
            elif infra:
                status = "infra_error"
            elif not applied:
                status = "apply_failed"
            else:
                status = "not_resolved"
            instances.append(
                {
                    "instance_id": instance_id,
                    "resolved": resolved,
                    "applied": applied,
                    "infra_failure": infra,
                    "status": status,
                }
            )
    resolved_count = sum(1 for item in instances if item.get("resolved"))
    applied_count = sum(1 for item in instances if item.get("applied"))
    completed = len(instances)
    return {
        "run_id": run_id,
        "model_name": model_name,
        "log_root": str(log_root),
        "completed": completed,
        "resolved_count": resolved_count,
        "applied_count": applied_count,
        "pass_rate": round(resolved_count / completed, 4) if completed else 0.0,
        "instances": instances,
    }


def _write_live_progress(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def _watch_eval_progress(
    *,
    run_id: str,
    model_name: str,
    expected: int,
    stop: threading.Event,
    live_path: Path | None,
    on_update: Callable[[dict[str, Any], dict[str, Any] | None], None] | None = None,
    poll_s: float = 2.0,
) -> None:
    """Poll harness logs and print / write progress as instances finish."""
    seen: set[str] = set()
    while not stop.wait(poll_s):
        try:
            progress = scan_eval_progress(run_id, model_name)
        except Exception:  # noqa: BLE001 — watcher must not kill the harness
            continue
        newly = [item for item in progress["instances"] if item["instance_id"] not in seen]
        for item in newly:
            seen.add(item["instance_id"])
            status = str(item.get("status") or ("RESOLVED" if item.get("resolved") else "not_resolved"))
            total = expected or "?"
            print(
                f"[Mango SWE-bench] eval {len(seen)}/{total} {item['instance_id']} "
                f"{status}  resolved={progress['resolved_count']}/{progress['completed']} "
                f"applied={progress.get('applied_count', 0)} "
                f"({float(progress['pass_rate']) * 100:.1f}%)",
                flush=True,
            )
            if on_update is not None:
                on_update(progress, item)
        live = {
            **progress,
            "expected": expected,
            "updated_at": time.time(),
        }
        _write_live_progress(live_path, live)
        if on_update is not None and not newly:
            on_update(progress, None)


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
    ready, reason = docker_daemon_ready()
    if not ready:
        raise EvaluationError(reason)

    pred_path = Path(predictions_path)
    # On Windows, wrap the official harness so patch.diff / eval.sh are written with
    # LF (CRLF breaks bash + git apply inside Linux eval containers).
    harness_module = (
        "mango_agent.benchmark.swebench.harness_winfix"
        if sys.platform == "win32"
        else "swebench.harness.run_evaluation"
    )
    cmd = [
        sys.executable,
        "-u",
        "-m",
        harness_module,
        "--dataset_name",
        dataset_name,
        "--split",
        split,
        "--predictions_path",
        str(pred_path),
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

    expected = count_predictions(pred_path, nonempty_only=True) or count_predictions(pred_path)
    live_path = Path(report_dir) / "eval_live.json" if report_dir is not None else None
    print(f"[Mango SWE-bench] running official harness: {' '.join(cmd)}", flush=True)
    live_hint = f" + {live_path}" if live_path else ""
    expect_hint = f" (expect ~{expected} instances)" if expected else ""
    print(f"[Mango SWE-bench] live progress -> terminal{live_hint}{expect_hint}", flush=True)

    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_eval_progress,
        kwargs={
            "run_id": run_id,
            "model_name": model_name,
            "expected": expected,
            "stop": stop,
            "live_path": live_path,
        },
        daemon=True,
        name="swebench-eval-progress",
    )
    watcher.start()

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            print(line, end="", flush=True)
        code = proc.wait()
    finally:
        stop.set()
        watcher.join(timeout=5.0)
        try:
            final_progress = scan_eval_progress(run_id, model_name)
            final_progress["expected"] = expected
            final_progress["updated_at"] = time.time()
            final_progress["done"] = True
            _write_live_progress(live_path, final_progress)
        except Exception:  # noqa: BLE001
            pass

    blob = "".join(lines)
    if code != 0:
        detail = blob.strip() or f"exit {code}"
        raise EvaluationError(f"SWE-bench harness failed ({code}): {detail[-2000:]}")

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

    progress = scan_eval_progress(run_id, model_name)
    instances: list[dict[str, Any]] = []
    log_root = Path(RUN_EVALUATION_LOG_DIR) / run_id / safe_model
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
    if not summary and progress["completed"]:
        payload["resolved_count"] = progress["resolved_count"]
        payload["total"] = progress["completed"]
        payload["pass_rate"] = progress["pass_rate"]
    return payload


def merge_harness_into_report(
    report_path: Path,
    harness_summary: dict[str, Any],
) -> Path | None:
    """Update an existing latest.json with harness resolved / pass_rate."""
    path = Path(report_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    resolved_map = {
        str(item["instance_id"]): bool(item.get("resolved"))
        for item in harness_summary.get("instances") or []
        if item.get("instance_id")
    }
    for item in payload.get("instances") or []:
        iid = str(item.get("instance_id") or "")
        if iid in resolved_map:
            item["resolved"] = resolved_map[iid]
            item["success"] = resolved_map[iid]
    resolved_count = int(harness_summary.get("resolved_count") or 0)
    total = int(harness_summary.get("total") or payload.get("task_count") or 0)
    payload["resolved"] = resolved_count
    payload["pass_rate"] = (
        float(harness_summary.get("pass_rate"))
        if harness_summary.get("pass_rate") is not None
        else (round(resolved_count / total, 4) if total else 0.0)
    )
    payload["harness_summary"] = {
        "run_id": harness_summary.get("run_id"),
        "resolved_count": resolved_count,
        "total": total,
        "pass_rate": payload["pass_rate"],
        "summary_path": harness_summary.get("summary_path"),
        "log_root": harness_summary.get("log_root"),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
