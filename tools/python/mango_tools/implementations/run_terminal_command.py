from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 60


def _run_shell_command(
    command: str,
    *,
    cwd: Path | None,
    timeout: int,
    shell: bool,
    cancelled: Any,
) -> dict[str, Any]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME"}}
    with tempfile.TemporaryDirectory(prefix="mango-cmd-") as tmp:
        out_path = Path(tmp) / "stdout.txt"
        err_path = Path(tmp) / "stderr.txt"
        started = time.monotonic()
        try:
            with out_path.open("w", encoding="utf-8", errors="replace") as out_f, err_path.open(
                "w", encoding="utf-8", errors="replace"
            ) as err_f:
                proc = subprocess.Popen(
                    command,
                    cwd=str(cwd) if cwd else None,
                    shell=shell,
                    stdin=subprocess.DEVNULL,
                    stdout=out_f,
                    stderr=err_f,
                    creationflags=flags,
                    env=env,
                )

                # Poll the process so we can react to cancellation promptly.
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
                        return {
                            "exit_code": -1,
                            "stdout": out_path.read_text(encoding="utf-8", errors="replace") if out_path.is_file() else "",
                            "stderr": "command cancelled",
                            "timed_out": False,
                        }
                    rc = proc.poll()
                    if rc is not None:
                        return {
                            "exit_code": rc,
                            "stdout": out_path.read_text(encoding="utf-8", errors="replace"),
                            "stderr": err_path.read_text(encoding="utf-8", errors="replace"),
                            "timed_out": False,
                        }
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
                        return {
                            "exit_code": -1,
                            "stdout": out_path.read_text(encoding="utf-8", errors="replace") if out_path.is_file() else "",
                            "stderr": f"command timed out after {timeout}s",
                            "timed_out": True,
                        }
                    time.sleep(0.1)
        finally:
            # TempDirectory cleanup happens automatically.
            pass


def run_terminal_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    shell: bool = True,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a shell command and capture stdout/stderr (requires UI confirm)."""
    if not command.strip():
        raise ValueError("command must not be empty")

    from mango_tools.confirm_gate import request_confirm

    preview = command.strip()
    if len(preview) > 180:
        preview = preview[:177] + "…"
    allowed = request_confirm(
        summary=f"Run shell command: {preview}",
        kind="shell",
        detail=command.strip(),
    )
    if not allowed:
        return {
            "command": command,
            "cwd": cwd,
            "exit_code": -1,
            "stdout": "",
            "stderr": "user_denied",
            "timed_out": False,
            "ok": False,
            "error": "user_denied",
        }

    cancelled = (_context or {}).get("_cancelled")

    if not cwd:
        workspace = (_context or {}).get("workspace")
        if workspace:
            cwd = str(workspace)

    workdir = Path(cwd).expanduser().resolve() if cwd else None
    if workdir is not None and not workdir.is_dir():
        raise FileNotFoundError(f"Working directory not found: {workdir}")

    if cancelled is not None and callable(cancelled) and cancelled():
        return {"exit_code": -1, "stdout": "", "stderr": "command cancelled", "timed_out": False}

    result = _run_shell_command(command, cwd=workdir, timeout=timeout, shell=shell, cancelled=cancelled)
    return {
        "command": command,
        "cwd": str(workdir) if workdir else None,
        "confirmed": True,
        **result,
    }
