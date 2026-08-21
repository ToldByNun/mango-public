"""Prepare SWE-bench repositories and collect model patches."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

from mango_agent.benchmark.swebench.instances import SweBenchInstance
from mango_agent.prompt import SWE_BENCH_SYSTEM_PROMPT


class WorkspaceError(Exception):
    pass


SWE_BENCH_DISABLED_TOOLS = frozenset(
    {"run_terminal_command", "write_file"}
)


def _run_git(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    cwd = Path(cwd)
    if not cwd.is_dir():
        raise WorkspaceError(f"git cwd is not a directory: {cwd}")
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise WorkspaceError(f"git {' '.join(args)} failed in {cwd}: {stderr}")
    return result


def _ensure_cached_repo(instance: SweBenchInstance, cache_root: Path) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    cached = cache_root / instance.repo.replace("/", "__")
    if cached.is_dir():
        return cached
    url = f"https://github.com/{instance.repo}.git"
    _run_git(["clone", "--filter=blob:none", url, str(cached)], cwd=cache_root, check=True)
    return cached


def _force_rmtree(path: Path) -> None:
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return

    def _onerror(func, item, _exc_info):  # noqa: ANN001
        try:
            os.chmod(item, stat.S_IWRITE)
            func(item)
        except OSError:
            pass

    shutil.rmtree(path, onerror=_onerror)
    if path.exists() and os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "rmdir", "/s", "/q", str(path)],
            check=False,
            capture_output=True,
        )
    if path.exists():
        time.sleep(0.25)
        shutil.rmtree(path, onerror=_onerror)


def _remove_worktree(cached: Path, dest: Path) -> None:
    dest = Path(dest).resolve()
    if cached.is_dir():
        _run_git(["worktree", "unlock", str(dest)], cwd=cached, check=False)
        _run_git(["worktree", "remove", "--force", str(dest)], cwd=cached, check=False)
        _run_git(["worktree", "prune", "--expire=now"], cwd=cached, check=False)
    _force_rmtree(dest)
    if cached.is_dir():
        _run_git(["worktree", "prune", "--expire=now"], cwd=cached, check=False)


def clone_or_copy_repo(instance: SweBenchInstance, dest: Path, cache_root: Path) -> None:
    dest = Path(dest).resolve()
    cache_root = Path(cache_root).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    if instance.local_repo_path:
        if dest.exists():
            _force_rmtree(dest)
        source = Path(instance.local_repo_path).expanduser().resolve()
        if not source.is_dir():
            raise WorkspaceError(f"local repo path does not exist: {source}")
        shutil.copytree(source, dest)
        return

    cached = _ensure_cached_repo(instance, cache_root).resolve()
    _run_git(["fetch", "origin", instance.base_commit, "--depth", "1"], cwd=cached, check=False)
    last_error: WorkspaceError | None = None
    for _attempt in range(2):
        _remove_worktree(cached, dest)
        try:
            _run_git(
                ["worktree", "add", "--detach", str(dest), instance.base_commit],
                cwd=cached,
                check=True,
            )
            break
        except WorkspaceError as exc:
            last_error = exc
            _remove_worktree(cached, dest)
    else:
        raise last_error or WorkspaceError(f"worktree was not created at {dest}")
    if not dest.is_dir():
        raise WorkspaceError(f"worktree was not created at {dest}")


def configure_git_identity(root: Path) -> None:
    _run_git(["config", "user.email", "mango@local"], cwd=root, check=False)
    _run_git(["config", "user.name", "Mango"], cwd=root, check=False)


def collect_model_patch(root: Path) -> str:
    diff = _run_git(["diff", "--no-color", "HEAD"], cwd=root, check=False)
    patch = (diff.stdout or "").strip()
    if patch:
        return patch
    cached = _run_git(["diff", "--no-color", "--cached", "HEAD"], cwd=root, check=False)
    return (cached.stdout or "").strip()


def cleanup_instance_workspace(
    instance: SweBenchInstance,
    root: Path,
    *,
    cache_root: Path | None = None,
) -> None:
    cache = cache_root or (Path.cwd() / ".mango" / "swebench" / "repo_cache")
    if instance.local_repo_path:
        if root.exists():
            _force_rmtree(root)
        return
    cached = cache / instance.repo.replace("/", "__")
    if cached.is_dir():
        _remove_worktree(cached, root)
    elif root.exists():
        _force_rmtree(root)


def prepare_instance_workspace(
    instance: SweBenchInstance,
    root: Path,
    *,
    cache_root: Path | None = None,
) -> None:
    cache = cache_root or (Path.cwd() / ".mango" / "swebench" / "repo_cache")
    clone_or_copy_repo(instance, root, cache)
    configure_git_identity(root)
    if instance.local_repo_path:
        commit = _run_git(["rev-parse", "HEAD"], cwd=root, check=True).stdout.strip()
        if instance.base_commit and commit != instance.base_commit:
            _run_git(["checkout", "-f", instance.base_commit], cwd=root, check=True)


def fail_to_pass_names(instance: SweBenchInstance) -> list[str]:
    raw = instance.data.get("FAIL_TO_PASS") or instance.data.get("fail_to_pass")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        raw = parsed
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    return []


def build_goal(instance: SweBenchInstance) -> str:
    parts = [
        "Fix the following GitHub issue in this repository.",
        "",
        instance.problem_statement.strip(),
    ]
    hints = instance.hints_text.strip()
    if hints:
        parts.extend(["", "Hints:", hints])
    failing = fail_to_pass_names(instance)
    if failing:
        parts.extend(["", "Failing tests (use these to locate the bug; do not edit tests unless required):"])
        parts.extend(f"- {name}" for name in failing[:20])
    parts.extend(
        [
            "",
            "Make the minimal code changes needed to resolve the issue.",
            "Use search_code / read_file to find the bug, then edit_file or edit_symbol to apply a small patch.",
            "If the exact library/API behavior is unclear, use ask_epistemic before editing.",
            "Do not rewrite whole files. Re-run the relevant failing tests before finalizing.",
        ]
    )
    return "\n".join(parts).strip()
