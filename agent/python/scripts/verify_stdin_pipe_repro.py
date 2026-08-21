"""Simulate serve stdin PIPE + run_tests in agent thread."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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


def run_variant(use_devnull: bool) -> dict[str, object]:
    from mango_tools.implementations.run_tests import _run_subprocess

    root = WORKSPACE.resolve()
    targets = [str(root / "test_math_utils.py")]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "--color=no",
        "--import-mode=importlib",
        "--rootdir",
        str(root),
        "-x",
        *targets,
    ]
    t0 = time.perf_counter()
    code, stdout, stderr, timed_out = _run_subprocess(cmd, cwd=root, timeout=15)
    return {
        "use_devnull_not_in_run_tests": use_devnull,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "exit_code": code,
        "timed_out": timed_out,
        "stdout_tail": stdout[-120:],
    }


def main() -> int:
    os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
    sys.path.insert(0, str(REPO / "tools" / "python"))

    results: list[dict[str, object]] = []

    def agent_worker() -> None:
        results.append(run_variant(False))

    threading.Thread(target=agent_worker, daemon=True).start()
    time.sleep(0.2)
    print("[stdin-pipe] main thread blocking on sys.stdin.readline() (serve_loop simulation)", flush=True)
    # In real serve this blocks forever until next JSONL command.
    # Here we timeout after 20s if agent thread hasn't finished.
    deadline = time.time() + 20
    while time.time() < deadline and len(results) == 0:
        time.sleep(0.05)
    if not results:
        print(json.dumps({"error": "agent thread did not finish within 20s"}))
        return 1
    print(json.dumps(results[0], indent=2))
    return 0 if not results[0].get("timed_out") else 1


if __name__ == "__main__":
    raise SystemExit(main())
