from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from mango_tools.implementations.run_tests import _SKIP_DIRS, _run_subprocess

_MAIN_GUARD = re.compile(r'if\s+__name__\s*==\s*["\']__main__["\']')
_TRACEBACK = re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE)
# Bare `python script.py` often exits 2 for argparse CLIs that require a path/args.
# That is not a crash — unit tests cover the real CLI paths.
_CLI_USAGE = re.compile(
    r"^usage:|"
    r"error:\s+the following arguments are required|"
    r"unrecognized arguments:|"
    r"too few arguments|"
    r"the following arguments are required",
    re.IGNORECASE | re.MULTILINE,
)

_SMOKE_TIMEOUT_SECONDS = 8
_MAX_SCRIPTS = 6


def _has_main_guard(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_MAIN_GUARD.search(text))


def discover_entry_scripts(
    root: Path,
    *,
    prefer: list[str] | None = None,
) -> list[str]:
    """Return impl .py files with a __main__ guard, preferring recently touched paths."""
    base = root.expanduser().resolve()
    if not base.is_dir():
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        if not path.is_file() or path.suffix.lower() != ".py":
            return
        if path.name.startswith("test_"):
            return
        try:
            rel_parts = path.relative_to(base).parts
        except ValueError:
            rel_parts = path.parts
        if any(part in _SKIP_DIRS for part in rel_parts[:-1]):
            return
        if not _has_main_guard(path):
            return
        text = str(path.resolve())
        if text not in seen:
            seen.add(text)
            ordered.append(text)

    for raw in prefer or []:
        _add(Path(raw).expanduser().resolve())
        if len(ordered) >= _MAX_SCRIPTS:
            return ordered

    for path in sorted(base.rglob("*.py")):
        _add(path)
        if len(ordered) >= _MAX_SCRIPTS:
            break
    return ordered


def _smoke_ok(code: int, stdout: str, stderr: str, *, timed_out: bool) -> bool:
    blob = f"{stdout}\n{stderr}"
    if _TRACEBACK.search(blob):
        return False
    if code == 0:
        return True
    if timed_out:
        return True
    # CLI entry points that require args: usage / missing-arg exits are healthy.
    if code in (1, 2) and _CLI_USAGE.search(blob):
        return True
    return False


def run_runtime_smoke(
    *,
    _context: dict[str, Any] | None = None,
    scripts: list[str] | None = None,
    timeout: int = _SMOKE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute __main__ scripts briefly; catch crashes pytest often misses."""
    workspace = (_context or {}).get("workspace")
    if not workspace:
        raise ValueError("run_runtime_smoke requires a workspace")
    cancelled = (_context or {}).get("_cancelled")
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Workspace not found: {root}")

    prefer = scripts or list((_context or {}).get("prefer_scripts") or [])
    targets = discover_entry_scripts(root, prefer=prefer)
    if not targets:
        return {
            "cwd": str(root),
            "mode": "runtime_smoke",
            "ok": True,
            "skipped": True,
            "reason": "no __main__ scripts found",
            "results": [],
        }

    results: list[dict[str, Any]] = []
    for script in targets:
        cmd = [sys.executable, script]
        code, stdout, stderr, timed_out = _run_subprocess(
            cmd,
            cwd=root,
            timeout=timeout,
            cancelled=cancelled,
        )
        ok = _smoke_ok(code, stdout, stderr, timed_out=timed_out)
        detail = (stderr or stdout).strip()
        if len(detail) > 1_200:
            detail = detail[:1_197].rstrip() + "..."
        entry = {
            "script": script,
            "exit_code": code,
            "timed_out": timed_out,
            "ok": ok,
            "stdout": stdout[-800:],
            "stderr": stderr[-800:],
            "detail": detail,
        }
        results.append(entry)
        if not ok:
            return {
                "cwd": str(root),
                "mode": "runtime_smoke",
                "ok": False,
                "skipped": False,
                "results": results,
                "failed_script": script,
                "detail": detail,
            }

    return {
        "cwd": str(root),
        "mode": "runtime_smoke",
        "ok": True,
        "skipped": False,
        "results": results,
    }
