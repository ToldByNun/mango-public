from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from mango_verification.config import CommandSpec
from mango_verification.types import StepResult

OUTPUT_CAP = 8_000


def run_command(project_path: str | Path, spec: CommandSpec) -> StepResult:
    if not spec.command.strip():
        return StepResult(command="", skipped=True)
    try:
        completed = subprocess.run(
            spec.command,
            cwd=str(Path(project_path).resolve()),
            shell=True,
            capture_output=True,
            text=True,
            timeout=spec.timeout,
            check=False,
            env=_isolated_env(),
        )
    except subprocess.TimeoutExpired as exc:
        output = _combine_output(exc.stdout, exc.stderr)
        return StepResult(
            command=spec.command,
            skipped=False,
            exit_code=-1,
            output=_cap_output(f"timed out after {spec.timeout}s\n{output}"),
        )
    output = _combine_output(completed.stdout, completed.stderr)
    return StepResult(
        command=spec.command,
        skipped=False,
        exit_code=int(completed.returncode),
        output=_cap_output(output),
    )


def clear_bytecode_caches(project_path: str | Path) -> None:
    """Drop __pycache__ so a fix-loop retest cannot reuse same-second bytecode."""
    root = Path(project_path).resolve()
    for path in root.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def _isolated_env() -> dict[str, str]:
    """Keep nested pytest/python from inheriting the outer session or stale .pyc files."""
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("PYTEST_"):
            env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(prefix="mango-pycache-")
    return env


def _combine_output(stdout: str | None, stderr: str | None) -> str:
    parts = [part for part in (stdout or "", stderr or "") if part]
    return "\n".join(parts).strip()


def _cap_output(output: str) -> str:
    text = output.strip()
    if len(text) > OUTPUT_CAP:
        return text[:OUTPUT_CAP] + "\n...[truncated]"
    return text
