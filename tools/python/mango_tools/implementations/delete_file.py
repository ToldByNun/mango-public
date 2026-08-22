"""delete_file — remove a file inside the workspace jail (A2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mango_tools.paths import file_tool_result, resolve_tool_path


def delete_file(
    path: str,
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    file_path = resolve_tool_path(path, _context)
    workspace = (_context or {}).get("workspace")
    if workspace:
        try:
            file_path.resolve().relative_to(Path(str(workspace)).resolve())
        except ValueError as exc:
            raise PermissionError(f"delete_file blocked outside workspace: {path}") from exc
    if not file_path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if file_path.is_dir():
        raise IsADirectoryError(f"delete_file refuses directories: {path}")
    file_path.unlink()
    return file_tool_result(file_path, _context, deleted=True)
