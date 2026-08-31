"""Path helpers for locating the Mango repo and Python runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from this file (or start) until runtime/config.yaml + agent/python exist."""
    cur = (start or Path(__file__).resolve()).parent
    for _ in range(12):
        if (cur / "runtime" / "config.yaml").is_file() and (cur / "agent" / "python").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    env = os.environ.get("MANGO_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd()


def python_executable(repo_root: Path) -> str:
    candidates = [
        repo_root / "python" / "python.exe",
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / "agent" / "python" / ".venv" / "Scripts" / "python.exe",
        repo_root / "python" / "bin" / "python",
        repo_root / ".venv" / "bin" / "python",
        repo_root / "agent" / "python" / ".venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return "python" if sys.platform == "win32" else "python3"


def python_package_paths(repo_root: Path) -> list[str]:
    dirs = [
        repo_root / "agent" / "python",
        repo_root / "tools" / "python",
        repo_root / "runtime" / "python",
        repo_root / "context" / "python",
        repo_root / "cot" / "python",
        repo_root / "epistemic" / "python",
        repo_root / "codeintel" / "python",
        repo_root / "verification" / "python",
        repo_root / "cli" / "python",
        # Host package itself (for studio bridge imports inside sidecar tools)
        repo_root / "apps" / "roblox-studio" / "host" / "python",
    ]
    return [str(p) for p in dirs if p.is_dir()]


def prompts_dir(repo_root: Path) -> str:
    return str(repo_root / "prompts")


def runtime_config_path(repo_root: Path) -> Path:
    env = os.environ.get("MANGO_RUNTIME_CONFIG", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    user = Path.home() / ".mango" / "runtime" / "config.yaml"
    if user.is_file():
        return user
    bundled = repo_root / "runtime" / "config.yaml"
    return bundled


def studio_workspace(session_id: str = "default") -> Path:
    dest = Path.home() / ".mango" / "studio" / (session_id or "default")
    dest.mkdir(parents=True, exist_ok=True)
    return dest
