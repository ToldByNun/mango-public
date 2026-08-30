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
    {
        "run_terminal_command",
        "write_file",
        # Local pytest/deps are not the SWE-bench grade path — Docker eval is.
        "run_tests",
        # Epistemic installs thrash small models away from locate→edit.
        "ask_epistemic",
    }
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
    """Return a source-focused git diff for the official harness.

    Prefer tracked Python/source paths so accidental junk files do not pollute
    the prediction. Fall back to the full tree diff if needed.
    """
    root = Path(root)
    source_globs = (
        "*.py",
        "*.pyi",
        "*.pyx",
        "*.pxd",
        "*.c",
        "*.cc",
        "*.cpp",
        "*.h",
        "*.hpp",
        "*.rs",
        "*.go",
        "*.js",
        "*.ts",
        "*.tsx",
        "*.jsx",
        "*.java",
        "*.rb",
        "*.php",
    )
    for pathspecs in (source_globs, ()):
        args = ["diff", "--no-color", "HEAD"]
        if pathspecs:
            args.extend(["--", *pathspecs])
        diff = _run_git(args, cwd=root, check=False)
        patch = _strip_test_paths_from_diff((diff.stdout or "").strip())
        if patch:
            return _normalize_patch_text(patch)
        cached_args = ["diff", "--no-color", "--cached", "HEAD"]
        if pathspecs:
            cached_args.extend(["--", *pathspecs])
        cached = _run_git(cached_args, cwd=root, check=False)
        patch = _strip_test_paths_from_diff((cached.stdout or "").strip())
        if patch:
            return _normalize_patch_text(patch)
    return ""


def _strip_test_paths_from_diff(patch: str) -> str:
    """Drop hunks that only touch test files (harness grades production code)."""
    if not patch.strip():
        return ""
    import re

    chunks = re.split(r"(?=^diff --git )", patch, flags=re.M)
    kept: list[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        # "diff --git a/foo.py b/foo.py"
        m = re.match(r"^diff --git a/(.+?) b/(.+?)\n", chunk)
        path = (m.group(2) if m else "").replace("\\", "/").lower()
        if any(
            part in path
            for part in (
                "/tests/",
                "/test/",
                "/testing/",
                "conftest.py",
                "/test_",
            )
        ) or path.startswith("test_") or "/test_" in path or path.endswith("_test.py"):
            continue
        # also basename test_*.py
        base = path.rsplit("/", 1)[-1]
        if base.startswith("test_") or base.endswith("_test.py"):
            continue
        kept.append(chunk)
    return "".join(kept).strip()


def _normalize_patch_text(patch: str) -> str:
    """Normalize a git diff for the official harness ``git apply``.

    Windows/worktree mode bits (100755 vs 100644) often make ``git apply`` fail
    inside Linux eval containers even when ``patch(1)`` would succeed — SWE-bench
    then marks ``patch_successfully_applied: false``.
    """
    import re

    text = patch.replace("\r\n", "\n").replace("\r", "\n")
    # Drop explicit mode-change hunks.
    text = re.sub(r"(?m)^old mode \d+\nnew mode \d+\n", "", text)
    # Force a stable mode on index lines: "index abc..def 100755" -> "... 100644"
    text = re.sub(
        r"(?m)^(index [0-9a-f]+\.\.[0-9a-f]+)(?: \d+)?$",
        r"\1 100644",
        text,
    )
    # "new file mode 100755" / "deleted file mode ..."
    text = re.sub(r"(?m)^(new file mode|deleted file mode) \d+$", r"\1 100644", text)
    text = text.strip()
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def patch_applies_cleanly(root: Path, patch: str) -> bool:
    """True when the working-tree diff reverses cleanly (i.e. matched HEAD→WT).

    The agent already applied edits in-tree; ``git apply --check`` against the
    dirty tree would fail. ``--reverse --check`` validates the hunk matches.
    """
    if not (patch or "").strip():
        return False
    root = Path(root)
    import tempfile

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        suffix=".diff",
        delete=False,
    ) as handle:
        handle.write(patch if patch.endswith("\n") else patch + "\n")
        tmp = Path(handle.name)
    try:
        check = _run_git(
            ["apply", "--reverse", "--check", str(tmp)],
            cwd=root,
            check=False,
        )
        return check.returncode == 0
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


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
            "Order: search_code or codebase_lookup → read_file on the implementation → "
            "one small edit_file (exact old_string from that read).",
            "Do not rewrite whole files. Do not edit tests first.",
            "After the patch parses (syntax OK), stop — the official Docker harness grades FAIL_TO_PASS.",
        ]
    )
    return "\n".join(parts).strip()
