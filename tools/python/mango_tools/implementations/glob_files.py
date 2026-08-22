"""glob_files — workspace-jailed glob with caps (A2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mango_tools.paths import resolve_tool_path

_DEFAULT_LIMIT = 200
_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def glob_files(
    pattern: str,
    *,
    path: str = ".",
    max_results: int = _DEFAULT_LIMIT,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not pattern or not str(pattern).strip():
        raise ValueError("glob_files requires a non-empty pattern")
    root = resolve_tool_path(path or ".", _context)
    workspace = (_context or {}).get("workspace")
    workspace_root = Path(str(workspace)).resolve() if workspace else None
    if workspace_root is not None:
        try:
            root.resolve().relative_to(workspace_root)
        except ValueError as exc:
            raise PermissionError(f"glob_files blocked outside workspace: {path}") from exc
    if not root.exists():
        raise FileNotFoundError(f"path not found: {path}")
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {path}")
    limit = max(1, min(int(max_results or _DEFAULT_LIMIT), 1000))
    matches: list[str] = []
    for match in root.rglob(pattern):
        if any(part in _SKIP_DIRS for part in match.parts):
            continue
        if not match.is_file():
            continue
        if workspace_root is not None:
            try:
                match.resolve().relative_to(workspace_root)
            except ValueError:
                continue
            rel = str(match.resolve().relative_to(workspace_root)).replace("\\", "/")
        else:
            rel = str(match)
        matches.append(rel)
        if len(matches) >= limit:
            break
    return {
        "pattern": pattern,
        "path": str(path or "."),
        "matches": matches,
        "count": len(matches),
        "truncated": len(matches) >= limit,
    }
