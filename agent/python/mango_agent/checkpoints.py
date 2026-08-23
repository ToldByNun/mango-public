"""Minimal file checkpoints before mutate/delete (A1).

Snapshots live under ``~/.mango/checkpoints/<session_id>/<stamp>_<hash>/``.
Retention is capped by count and total bytes. Disable with ``MANGO_FILE_CHECKPOINTS=0``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mango_agent.flags import file_checkpoints_enabled

MUTATING_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "insert_lines",
        "edit_symbol",
        "rename_symbol",
        "delete_file",
    }
)

DEFAULT_MAX_ENTRIES = 20
DEFAULT_MAX_BYTES = 500 * 1024 * 1024

# The agent loop snapshots from its thread while the UI may call undo from the
# serve executor thread. Serialize both so undo never races a snapshot.
_CHECKPOINT_LOCK = threading.Lock()


@dataclass(frozen=True)
class CheckpointInfo:
    checkpoint_id: str
    session_id: str
    root: Path
    paths: list[str]
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "root": str(self.root),
            "paths": list(self.paths),
            "created_at": self.created_at,
        }


def checkpoints_root() -> Path:
    override = os.environ.get("MANGO_CHECKPOINTS_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
    else:
        path = Path.home() / ".mango" / "checkpoints"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_dir(session_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (session_id or "default"))[:80]
    path = checkpoints_root() / (safe or "default")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_path(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, dest)
    elif src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)


def snapshot_paths(
    paths: list[str | Path],
    *,
    session_id: str = "default",
    workspace: str | Path | None = None,
) -> CheckpointInfo | None:
    """Copy current bytes (or mark missing) for each path. Returns None when disabled."""
    if not file_checkpoints_enabled():
        return None
    resolved: list[Path] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute() and workspace is not None:
            path = Path(workspace) / path
        resolved.append(path.expanduser())
    if not resolved:
        return None

    stamp = time.strftime("%Y%m%dT%H%M%S")
    digest = hashlib.sha1("|".join(str(p) for p in resolved).encode("utf-8")).hexdigest()[:10]
    checkpoint_id = f"{stamp}_{digest}"
    root = _session_dir(session_id) / checkpoint_id
    with _CHECKPOINT_LOCK:
        # Same-second snapshots of the same paths must not collide.
        if root.exists():
            checkpoint_id = f"{checkpoint_id}_{time.monotonic_ns() % 1_000_000}"
            root = _session_dir(session_id) / checkpoint_id
        root.mkdir(parents=True, exist_ok=True)
        meta_paths: list[str] = []
        for path in resolved:
            rel = path.name
            try:
                if workspace is not None:
                    rel = str(path.resolve().relative_to(Path(workspace).resolve()))
            except Exception:
                rel = path.name
            dest = root / "files" / rel
            marker = root / "missing" / rel
            meta_paths.append(rel.replace("\\", "/"))
            if path.exists():
                _copy_path(path, dest)
            else:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("missing\n", encoding="utf-8")
        info = CheckpointInfo(
            checkpoint_id=checkpoint_id,
            session_id=session_id or "default",
            root=root,
            paths=meta_paths,
            created_at=time.time(),
        )
        (root / "meta.json").write_text(
            json.dumps(info.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        prune_checkpoints(session_id=session_id)
    return info


def restore_checkpoint(
    checkpoint_id: str,
    *,
    session_id: str = "default",
    workspace: str | Path | None = None,
) -> list[str]:
    """Restore files from a checkpoint. Returns restored relative paths."""
    root = _session_dir(session_id) / checkpoint_id
    if not root.is_dir():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_id}")
    workspace_root = Path(workspace).resolve() if workspace else Path.cwd()
    restored: list[str] = []
    files_root = root / "files"
    missing_root = root / "missing"
    # Deepest first so restoring a/b/c.txt never fails on a missing parent that a
    # sibling delete removed earlier.
    with _CHECKPOINT_LOCK:
        if files_root.is_dir():
            for src in sorted(files_root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if not src.is_file():
                    continue
                rel = src.relative_to(files_root)
                dest = workspace_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored.append(str(rel).replace("\\", "/"))
        if missing_root.is_dir():
            for marker in sorted(missing_root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if not marker.is_file():
                    continue
                rel = marker.relative_to(missing_root)
                dest = workspace_root / rel
                if dest.is_file():
                    dest.unlink()
                elif dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)
                restored.append(str(rel).replace("\\", "/"))
    return sorted(set(restored))


def latest_checkpoint_id(session_id: str = "default") -> str | None:
    entries = _checkpoint_entries(session_id)
    return entries[0][0].name if entries else None


def _checkpoint_entries(session_id: str) -> list[tuple[Path, float]]:
    """Checkpoints newest-first as (path, sort_key). Stamp prefix keeps it monotonic."""
    session = _session_dir(session_id)
    try:
        candidates = [p for p in session.iterdir() if p.is_dir() and (p / "meta.json").is_file()]
    except OSError:
        return []

    def _sort_key(path: Path) -> float:
        stamp = path.name.split("_")[0]
        try:
            return time.strptime(stamp, "%Y%m%dT%H%M%S") and path.stat().st_mtime
        except (ValueError, OSError):
            return path.stat().st_mtime

    return sorted(((p, _sort_key(p)) for p in candidates), key=lambda item: item[1], reverse=True)


def undo_last_mutation(
    *,
    session_id: str = "default",
    workspace: str | Path | None = None,
    consumed: set[str] | None = None,
) -> dict[str, Any]:
    """Undo the most recent mutation, then pop that checkpoint so the next undo
    walks further back through the run's history."""
    with _CHECKPOINT_LOCK:
        entries = _checkpoint_entries(session_id)
        target: Path | None = None
        for path, _key in entries:
            if consumed is None or path.name not in consumed:
                target = path
                break
        if target is None:
            return {"ok": False, "error": "no checkpoint"}
        if consumed is not None:
            consumed.add(target.name)
    restored = restore_checkpoint(target.name, session_id=session_id, workspace=workspace)
    return {
        "ok": True,
        "checkpoint_id": target.name,
        "restored": restored,
        "undo_depth": sum(1 for name in (consumed or set()) if name),
    }


def prune_checkpoints(
    *,
    session_id: str = "default",
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> None:
    session = _session_dir(session_id)
    entries = sorted(
        [p for p in session.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    total = 0
    keep: list[Path] = []
    for entry in entries:
        size = _dir_size(entry)
        if len(keep) >= max_entries or total + size > max_bytes:
            shutil.rmtree(entry, ignore_errors=True)
            continue
        keep.append(entry)
        total += size


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except Exception:
        return total
    return total


def paths_for_tool_call(name: str, arguments: dict[str, Any] | None) -> list[str]:
    args = arguments or {}
    paths: list[str] = []
    for key in ("path", "file", "target"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value.strip())
    if name == "rename_symbol":
        # rename may touch a directory tree; snapshot the path root when given.
        pass
    return paths
