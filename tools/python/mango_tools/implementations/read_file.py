from __future__ import annotations

from typing import Any

from mango_tools.paths import file_tool_result, resolve_tool_path


def read_file(
    path: str,
    *,
    encoding: str = "utf-8",
    max_bytes: int | None = None,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read a file from disk and return its contents."""
    file_path = resolve_tool_path(path, _context)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    if max_bytes is not None and file_path.stat().st_size > max_bytes:
        data = file_path.read_bytes()[:max_bytes]
        content = data.decode(encoding, errors="replace")
        truncated = True
    else:
        content = file_path.read_text(encoding=encoding)
        truncated = False

    return file_tool_result(
        file_path,
        _context,
        content=content,
        truncated=truncated,
        size_bytes=file_path.stat().st_size,
    )
