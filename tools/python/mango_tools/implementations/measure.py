"""Repeat a short command and report wall-clock samples."""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_REPEATS = 5
MAX_REPEATS = 15
DEFAULT_TIMEOUT_SECONDS = 30


def _run_once(
    command: str,
    *,
    cwd: Path | None,
    timeout: float,
    cancelled: Any,
) -> tuple[int, str, bool]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME"}}
    with tempfile.TemporaryDirectory(prefix="mango-measure-") as tmp:
        out_path = Path(tmp) / "stdout.txt"
        err_path = Path(tmp) / "stderr.txt"
        started = time.monotonic()
        with out_path.open("w", encoding="utf-8", errors="replace") as out_f, err_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as err_f:
            proc = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
                creationflags=flags,
                env=env,
            )
            while True:
                if cancelled is not None and callable(cancelled) and cancelled():
                    _kill(proc)
                    stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
                    return -1, stderr or "command cancelled", False
                rc = proc.poll()
                if rc is not None:
                    stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
                    return rc, stderr, False
                if time.monotonic() - started > timeout:
                    _kill(proc)
                    stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.is_file() else ""
                    return -1, stderr, True
                time.sleep(0.05)


def _kill(proc: subprocess.Popen[Any]) -> None:
    try:
        proc.terminate()
    except Exception:
        pass
    time.sleep(0.1)
    try:
        proc.kill()
    except Exception:
        pass


def measure(
    command: str,
    *,
    repeats: int = DEFAULT_REPEATS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    cwd: str | None = None,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run `command` several times and return median wall time in milliseconds."""
    if not str(command or "").strip():
        raise ValueError("command must not be empty")

    ctx = _context or {}
    cancelled = ctx.get("_cancelled")
    n = max(1, min(int(repeats or DEFAULT_REPEATS), MAX_REPEATS))
    budget = max(1, int(timeout or DEFAULT_TIMEOUT_SECONDS))

    if not cwd:
        workspace = ctx.get("workspace")
        if workspace:
            cwd = str(workspace)
    workdir = Path(cwd).expanduser().resolve() if cwd else None
    if workdir is not None and not workdir.is_dir():
        raise FileNotFoundError(f"Working directory not found: {workdir}")

    samples_ms: list[float] = []
    stderr_parts: list[str] = []
    ok_any = False
    deadline = time.monotonic() + budget
    for _ in range(n):
        if cancelled is not None and callable(cancelled) and cancelled():
            return {
                "ok": False,
                "command": command,
                "samples_ms": samples_ms,
                "median_ms": _median(samples_ms),
                "stderr": "command cancelled",
            }
        remaining = deadline - time.monotonic()
        if remaining <= 0.2:
            break
        started = time.perf_counter()
        code, stderr, timed_out = _run_once(
            command,
            cwd=workdir,
            timeout=max(0.5, remaining),
            cancelled=cancelled,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        samples_ms.append(round(elapsed_ms, 3))
        err = str(stderr or "").strip()
        if err:
            stderr_parts.append(err[-800:])
        if code == 0 and not timed_out:
            ok_any = True

    return {
        "ok": ok_any and bool(samples_ms),
        "command": command,
        "samples_ms": samples_ms,
        "median_ms": _median(samples_ms),
        "stderr": "\n".join(stderr_parts)[-2_000:],
    }


def _median(samples: list[float]) -> float | None:
    if not samples:
        return None
    return round(float(statistics.median(samples)), 3)
