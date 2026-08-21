"""Step 3a: isolate GGUF + run_tests interaction (no agent loop).

Variants:
  A - run_tests while ModelRunner.complete() is actively inferencing (parallel threads)
  B - run_tests after model is loaded and idle (no active completion)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKSPACE = Path(
    os.environ.get(
        "MANGO_REPRO_WORKSPACE",
        r"C:\Users\mikaj\AppData\Local\Temp\mango-step1-gqcdmyw0",
    )
)
CONFIG = REPO / "runtime" / "config.yaml"
TIMEOUT_WARN_S = 10.0


def _bootstrap() -> None:
    os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
    sys.path[:0] = [
        str(REPO / "tools" / "python"),
        str(REPO / "runtime" / "python"),
        str(REPO / "agent" / "python"),
    ]


def _mem_snapshot() -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {}
    try:
        import psutil

        proc = psutil.Process()
        out["rss_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
        out["vms_mb"] = round(proc.memory_info().vms / (1024 * 1024), 1)
        vm = psutil.virtual_memory()
        out["sys_avail_mb"] = round(vm.available / (1024 * 1024), 1)
        out["sys_used_pct"] = round(vm.percent, 1)
    except Exception as exc:  # noqa: BLE001
        out["psutil_error"] = str(exc)
    return out


def _gpu_snapshot() -> dict[str, str]:
    import subprocess

    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            used, total, util = [part.strip() for part in proc.stdout.strip().split(",")]
            return {
                "gpu_mem_used_mb": used,
                "gpu_mem_total_mb": total,
                "gpu_util_pct": util,
            }
    except Exception as exc:  # noqa: BLE001
        return {"gpu_error": str(exc)}
    return {"gpu_error": "nvidia-smi unavailable"}


def _ensure_workspace() -> Path:
    ws = WORKSPACE.resolve()
    if not (ws / "math_utils.py").is_file() or not (ws / "test_math_utils.py").is_file():
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "math_utils.py").write_text(
            "def clamp(val, min_val, max_val):\n"
            "    if val < min_val:\n"
            "        return min_val\n"
            "    if val > max_val:\n"
            "        return max_val\n"
            "    return val\n",
            encoding="utf-8",
        )
        (ws / "test_math_utils.py").write_text(
            "from math_utils import clamp\n\n"
            "def test_clamp():\n"
            "    assert clamp(5, 1, 10) == 5\n"
            "    assert clamp(0, 1, 10) == 1\n"
            "    assert clamp(15, 1, 10) == 10\n",
            encoding="utf-8",
        )
    return ws


def _run_tests_once(label: str) -> dict[str, object]:
    from mango_tools.implementations.run_tests import _TEST_TIMEOUT_SECONDS, run_tests

    ctx = {"workspace": str(_ensure_workspace())}
    t0 = time.perf_counter()
    result = run_tests(_context=ctx)
    elapsed = time.perf_counter() - t0
    payload = {
        "label": label,
        "elapsed_s": round(elapsed, 3),
        "ok": result.get("ok"),
        "timed_out": result.get("timed_out"),
        "exit_code": result.get("exit_code"),
        "timeout_config_s": _TEST_TIMEOUT_SECONDS,
        "stderr_tail": (result.get("stderr") or "")[-300:],
        "stdout_tail": (result.get("stdout") or "")[-300:],
    }
    if elapsed >= TIMEOUT_WARN_S:
        payload["warning"] = "slow_or_hung"
    return payload


def variant_b_idle_model() -> dict[str, object]:
    from mango_runtime import ModelRunner

    runner = ModelRunner(str(CONFIG))
    print("[3a-B] loading model...", flush=True)
    t_load = time.perf_counter()
    runner.load()
    load_s = round(time.perf_counter() - t_load, 3)
    mem_after_load = _mem_snapshot()
    gpu_after_load = _gpu_snapshot()
    print(f"[3a-B] model loaded in {load_s}s mem={mem_after_load} gpu={gpu_after_load}", flush=True)

    test_result = _run_tests_once("B_idle_after_load")
    runner.unload()
    return {
        "variant": "B_idle_after_load",
        "model_load_s": load_s,
        "mem_after_load": mem_after_load,
        "gpu_after_load": gpu_after_load,
        "run_tests": test_result,
    }


def variant_a_parallel_inference() -> dict[str, object]:
    from mango_runtime import ModelRunner

    runner = ModelRunner(str(CONFIG))
    print("[3a-A] loading model...", flush=True)
    runner.load()
    mem_after_load = _mem_snapshot()
    gpu_after_load = _gpu_snapshot()

    infer_state = {"done": False, "started": False, "error": None, "elapsed_s": None}
    test_state: dict[str, object] = {"started": False}
    infer_lock = threading.Lock()

    def infer_worker() -> None:
        prompt = (
            "Write a Python module with clamp(val, min_val, max_val) and explain edge cases. "
            "Include several paragraphs of reasoning before any code."
        )
        infer_state["started"] = True
        t0 = time.perf_counter()
        try:
            with infer_lock:
                runner.complete(
                    prompt,
                    max_tokens=256,
                    force_grammar=False,
                    reset_cache=True,
                )
        except Exception as exc:  # noqa: BLE001
            infer_state["error"] = str(exc)
        finally:
            infer_state["elapsed_s"] = round(time.perf_counter() - t0, 3)
            infer_state["done"] = True

    def tests_worker() -> None:
        # Wait until inference visibly started, then overlap run_tests with active generation.
        deadline = time.monotonic() + 30
        while not infer_state["started"] and time.monotonic() < deadline:
            time.sleep(0.01)
        test_state["started"] = True
        test_state["infer_running_at_start"] = not infer_state["done"]
        test_state["result"] = _run_tests_once("A_parallel_while_inferring")

    infer_thread = threading.Thread(target=infer_worker, name="infer", daemon=True)
    tests_thread = threading.Thread(target=tests_worker, name="run_tests", daemon=True)

    t0 = time.perf_counter()
    infer_thread.start()
    tests_thread.start()
    infer_thread.join()
    tests_thread.join()
    total_s = round(time.perf_counter() - t0, 3)

    runner.unload()
    return {
        "variant": "A_parallel_while_inferring",
        "mem_after_load": mem_after_load,
        "gpu_after_load": gpu_after_load,
        "infer": infer_state,
        "run_tests": test_state.get("result"),
        "infer_running_at_test_start": test_state.get("infer_running_at_start"),
        "total_parallel_window_s": total_s,
    }


def variant_agent_like_sequential() -> dict[str, object]:
    """Same process/thread: grammar completes then run_tests (matches agent ordering)."""
    from mango_runtime import ModelRunner

    runner = ModelRunner(str(CONFIG))
    runner.load()
    timings: list[float] = []
    for i in range(3):
        t0 = time.perf_counter()
        runner.complete(
            "Implement clamp(val, min_val, max_val) in math_utils.py",
            max_tokens=128,
            force_grammar=True,
            reset_cache=(i == 0),
        )
        timings.append(round(time.perf_counter() - t0, 3))
    test_result = _run_tests_once("agent_like_sequential")
    runner.unload()
    return {
        "variant": "agent_like_sequential_same_thread",
        "complete_timings_s": timings,
        "run_tests": test_result,
    }


def main() -> int:
    _bootstrap()
    ws = _ensure_workspace()
    print(f"[3a] workspace={ws}", flush=True)
    print(f"[3a] baseline mem={_mem_snapshot()} gpu={_gpu_snapshot()}", flush=True)

    results = [
        variant_b_idle_model(),
        variant_a_parallel_inference(),
        variant_agent_like_sequential(),
    ]
    print("\n[3a] SUMMARY", flush=True)
    print(json.dumps(results, indent=2), flush=True)

    hung = [
        r["run_tests"]
        for r in results
        if isinstance(r.get("run_tests"), dict)
        and (r["run_tests"].get("timed_out") or (r["run_tests"].get("elapsed_s") or 0) >= TIMEOUT_WARN_S)
    ]
    if hung:
        print(f"[3a] HANG/SLOW detected in {len(hung)} variant(s)", flush=True)
        return 1
    print("[3a] PASS all variants finished quickly", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
