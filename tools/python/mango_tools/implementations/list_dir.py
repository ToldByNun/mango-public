"""list_dir — list entries under a workspace path (A2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mango_tools.paths import resolve_tool_path

_DEFAULT_LIMIT = 200


def list_dir(
    path: str = ".",
    *,
    max_entries: int = _DEFAULT_LIMIT,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = resolve_tool_path(path or ".", _context)
    workspace = (_context or {}).get("workspace")
    if workspace:
        try:
            root.resolve().relative_to(Path(str(workspace)).resolve())
        except ValueError as exc:
            raise PermissionError(f"list_dir blocked outside workspace: {path}") from exc
    if not root.exists():
        raise FileNotFoundError(f"path not found: {path}")
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {path}")
    limit = max(1, min(int(max_entries or _DEFAULT_LIMIT), 1000))
    entries: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if len(entries) >= limit:
            break
        rel = child.name
        try:
            if workspace:
                rel = str(child.resolve().relative_to(Path(str(workspace)).resolve())).replace("\\", "/")
        except Exception:
            rel = child.name
        entries.append(
            {
                "name": child.name,
                "path": rel,
                "type": "dir" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else None,
            }
        )
    return {
        "path": str(path or "."),
        "entries": entries,
        "count": len(entries),
        "truncated": len(entries) >= limit,
    }
