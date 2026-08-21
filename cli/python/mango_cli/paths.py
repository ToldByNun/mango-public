from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_CONFIG = """# Mango runtime config (auto-created).
# Set model.path to your GGUF, or copy from the Mango install's runtime/config.yaml.

model:
  path: ""
  n_ctx: 16384
  n_batch: 2048
  n_ubatch: 512

hardware:
  n_gpu_layers: -1
  n_threads: 0

inference:
  max_tokens: 2048
  temperature: 0.1
  top_p: 0.95
  stop: []
"""


def find_repo_root(start: Path | None = None) -> Path | None:
    """Find the Mango/Mango install root (runtime/config.yaml + agent/python)."""
    starts = []
    if start is not None:
        starts.append(Path(start).expanduser().resolve())
    starts.append(Path(__file__).resolve())
    starts.append(Path.cwd().resolve())
    env = os.environ.get("MANGO_HOME")
    if env:
        starts.insert(0, Path(env).expanduser().resolve())

    seen: set[Path] = set()
    for origin in starts:
        here = origin if origin.is_dir() else origin.parent
        for candidate in (here, *here.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            if _is_install_root(candidate):
                return candidate
    return None


def _is_install_root(path: Path) -> bool:
    return (path / "agent" / "python").is_dir() and (
        (path / "runtime" / "config.yaml").is_file()
        or (path / "runtime" / "config.example.yaml").is_file()
        or (path / "apps" / "electron").is_dir()
    )


def install_runtime_config(repo_root: Path | None = None) -> Path | None:
    root = repo_root if repo_root is not None else find_repo_root()
    if root is None:
        return None
    for name in ("config.yaml", "config.yml", "config.example.yaml"):
        candidate = root / "runtime" / name
        if candidate.is_file():
            return candidate
    return None


def mango_dir(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".mango"


def workspace_config_path(workspace: Path) -> Path:
    return mango_dir(workspace) / "config.yaml"


def _env_config() -> Path | None:
    raw = os.environ.get("MANGO_RUNTIME_CONFIG")
    if raw:
        return Path(raw).expanduser().resolve()
    return None


def ensure_workspace_config(workspace: Path, *, seed: Path | None = None) -> Path:
    """Create `.mango/config.yaml` in the project if missing.

    Seeds from the Mango install config when available so local GGUF paths carry over.
    Migrates `.devdeck/config.yaml` if that is the only existing file.
    """
    dest = workspace_config_path(workspace)
    if dest.is_file():
        return dest

    workspace = Path(workspace).expanduser().resolve()
    legacy = workspace / ".devdeck" / "config.yaml"
    mango_dir(workspace).mkdir(parents=True, exist_ok=True)

    source = seed if seed is not None and seed.is_file() else None
    if source is None and legacy.is_file():
        source = legacy
    if source is None:
        source = install_runtime_config()

    if source is not None and source.is_file():
        dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        dest.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    return dest


def resolve_cli_config(workspace: Path, explicit: Path | None = None) -> Path:
    env = _env_config()
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    if env is not None:
        return env
    return ensure_workspace_config(workspace)


def runtime_config_path(repo_root: Path | None = None) -> Path:
    env = _env_config()
    if env is not None:
        return env
    installed = install_runtime_config(repo_root)
    if installed is not None:
        return installed
    root = repo_root or find_repo_root() or Path.cwd()
    return Path(root) / "runtime" / "config.yaml"


def default_workspace(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()).resolve()
