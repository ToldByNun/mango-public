from __future__ import annotations

from typing import Any

from mango_tools.fuzzy_edit import apply_replace
from mango_tools.paths import file_tool_result, resolve_tool_path
from mango_tools.syntax import python_syntax_error


def edit_file(
    path: str,
    old_string: str,
    new_string: str,
    *,
    encoding: str = "utf-8",
    replace_all: bool = False,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace old_string with new_string in a file."""
    file_path = resolve_tool_path(path, _context)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    context = _context or {}
    files_read = {str(item) for item in (context.get("files_read") or ())}
    require_grounded = bool(context.get("require_grounded_edits"))
    abs_path = str(file_path.resolve())
    allow_fuzzy = True
    if require_grounded:
        if abs_path not in files_read:
            allow_fuzzy = False
        else:
            # After read_file: exact and newline-normalized only (no fuzzy/indent/whitespace).
            allow_fuzzy = False

    content = file_path.read_text(encoding=encoding)
    updated, replacements, match = apply_replace(
        content,
        old_string,
        new_string,
        replace_all=replace_all,
        allow_fuzzy=allow_fuzzy,
    )

    file_path.write_text(updated, encoding=encoding)
    result = file_tool_result(
        file_path,
        _context,
        replacements=replacements,
        bytes_written=len(updated.encode(encoding)),
        match=match,
    )
    if match not in {"exact", "newlines"}:
        result["fuzzy"] = True
    syntax_error = python_syntax_error(file_path, source=updated)
    if syntax_error:
        result["syntax_error"] = syntax_error
    return result
