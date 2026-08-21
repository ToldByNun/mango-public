from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_TEST_TIMEOUT_SECONDS = 60
_SKIP_DIRS = frozenset({".mango", ".devdeck", ".pytest_cache", ".venv", "venv", "__pycache__", ".git", "node_modules"})


def _discover_pytest_targets(root: Path) -> list[str]:
    targets: list[str] = []
    for path in sorted(root.rglob("test_*.py")):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            rel_parts = path.parts
        if any(part in _SKIP_DIRS for part in rel_parts[:-1]):
            continue
        targets.append(str(path.resolve()))
        if len(targets) >= 8:
            break
    return targets


def _pytest_env(workspace: Path) -> dict[str, str]:
    """Isolate pytest from the agent/sidecar import path but keep workspace imports."""
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(workspace.resolve())
    return env


def _run_subprocess(
    cmd: list[str], *, cwd: Path, timeout: int, cancelled: Any,
) -> tuple[int, str, str, bool]:
    """Run a command with stdout/stderr redirected to files (avoids pipe deadlocks)."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with tempfile.TemporaryDirectory(prefix="mango-pytest-") as tmp:
        out_path = Path(tmp) / "stdout.txt"
        err_path = Path(tmp) / "stderr.txt"
        started = time.monotonic()
        try:
            with out_path.open("w", encoding="utf-8", errors="replace") as out_f, err_path.open(
                "w",
                encoding="utf-8",
                errors="replace",
            ) as err_f:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdin=subprocess.DEVNULL,
                    stdout=out_f,
                    stderr=err_f,
                    creationflags=flags,
                    env=_pytest_env(cwd),
                )

                while True:
                    if cancelled is not None and callable(cancelled) and cancelled():
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        time.sleep(0.15)
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        stdout = out_path.read_text(encoding="utf-8", errors="replace")[-4_000:] if out_path.is_file() else ""
                        stderr = out_path.read_text(encoding="utf-8", errors="replace")[-2_000:] if err_path.is_file() else ""
                        return -1, stdout, stderr, False

                    rc = proc.poll()
                    if rc is not None:
                        stdout = out_path.read_text(encoding="utf-8", errors="replace")[-4_000:]
                        stderr = err_path.read_text(encoding="utf-8", errors="replace")[-2_000:]
                        return rc, stdout, stderr, False

                    if time.monotonic() - started > timeout:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        time.sleep(0.15)
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        stdout = out_path.read_text(encoding="utf-8", errors="replace")[-4_000:] if out_path.is_file() else ""
                        stderr = out_path.read_text(encoding="utf-8", errors="replace")[-2_000:] if err_path.is_file() else ""
                        return -1, stdout, stderr, True

                    time.sleep(0.1)
        finally:
            pass


def run_tests(
    *,
    _context: dict[str, Any] | None = None,
    test_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Run pytest in the workspace and return the compact report."""
    workspace = (_context or {}).get("workspace")
    if not workspace:
        raise ValueError("run_tests requires a workspace")
    cancelled = (_context or {}).get("_cancelled")
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Workspace not found: {root}")

    targets: list[str] = []
    if test_paths:
        targets = [str(Path(p).expanduser().resolve()) for p in test_paths if Path(p).is_file()]
    if not targets:
        targets = _discover_pytest_targets(root)

    if not targets:
        return {
            "cwd": str(root),
            "mode": "pytest",
            "exit_code": 5,
            "ok": False,
            "timed_out": False,
            "targets": [],
            "stdout": "",
            "stderr": f"No test_*.py files found in workspace: {root}",
        }

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
    code, stdout, stderr, timed_out = _run_subprocess(
        cmd, cwd=root, timeout=_TEST_TIMEOUT_SECONDS, cancelled=cancelled,
    )
    names = ", ".join(Path(t).name for t in targets)
    header = f"targets: {names}\n"
    if timed_out:
        message = f"pytest timed out after {_TEST_TIMEOUT_SECONDS}s (targets: {names})"
        stderr = f"{message}\n{stderr}".strip()
        return {
            "cwd": str(root),
            "mode": "pytest",
            "exit_code": -1,
            "ok": False,
            "timed_out": True,
            "targets": targets,
            "stdout": header + stdout,
            "stderr": stderr,
        }
    return {
        "cwd": str(root),
        "mode": "pytest",
        "exit_code": code,
        "ok": code == 0,
        "timed_out": False,
        "targets": targets,
        "stdout": header + stdout,
        "stderr": stderr,
    }
