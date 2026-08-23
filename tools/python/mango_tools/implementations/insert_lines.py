from __future__ import annotations

from typing import Any

from mango_tools.paths import ensure_inside_workspace, file_tool_result, resolve_tool_path
from mango_tools.syntax import python_syntax_error


def insert_lines(
    path: str,
    line: int,
    content: str,
    *,
    encoding: str = "utf-8",
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert text at a 1-based line number without rewriting the whole file."""
    file_path = resolve_tool_path(path, _context)
    ensure_inside_workspace(file_path, _context, tool="insert_lines")
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    text = (content or "")
    if not text.strip():
        raise ValueError("insert_lines content is empty. Pass the lines to add.")

    existing = file_path.read_text(encoding=encoding)
    file_lines = existing.splitlines(keepends=True)
    if existing and not file_lines:
        file_lines = [existing]

    # Preserve whether the file ended with a newline.
    had_trailing_newline = existing.endswith(("\n", "\r\n"))
    if file_lines and not had_trailing_newline:
        last = file_lines[-1]
        if last.endswith(("\n", "\r\n")):
            file_lines[-1] = last.rstrip("\r\n")

    insert_line = int(line)
    if insert_line < 1:
        insert_line = len(file_lines) + 1

    new_lines = text.splitlines(keepends=True)
    if text and not text.endswith(("\n", "\r\n")):
        if new_lines:
            new_lines[-1] = new_lines[-1].rstrip("\r\n") + "\n"
        else:
            new_lines = [text + "\n"]

    # line N inserts before the current line N (content becomes line N).
    idx = min(max(insert_line - 1, 0), len(file_lines))
    updated_lines = [*file_lines[:idx], *new_lines, *file_lines[idx:]]
    updated = "".join(updated_lines)
    if had_trailing_newline and updated and not updated.endswith(("\n", "\r\n")):
        updated += "\n"

    file_path.write_text(updated, encoding=encoding)
    result = file_tool_result(
        file_path,
        _context,
        line=insert_line,
        lines_inserted=len(new_lines),
        bytes_written=len(updated.encode(encoding)),
    )
    result["line_count"] = len(updated.splitlines())
    syntax_error = python_syntax_error(file_path, source=updated)
    if syntax_error:
        result["syntax_error"] = syntax_error
    return result
