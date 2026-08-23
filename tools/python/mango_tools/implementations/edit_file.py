from __future__ import annotations

from typing import Any

from mango_tools.fuzzy_edit import apply_replace
from mango_tools.paths import ensure_inside_workspace, file_tool_result, resolve_tool_path
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
    ensure_inside_workspace(file_path, _context, tool="edit_file")
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    context = _context or {}
    files_read = {str(item) for item in (context.get("files_read") or ())}
    require_grounded = bool(context.get("require_grounded_edits"))
    abs_path = str(file_path.resolve())

    allow_fuzzy = True
    allow_whitespace = True
    allow_indent = True
    if require_grounded:
        if abs_path not in files_read:
            allow_fuzzy = False
            allow_whitespace = False
            allow_indent = False
        else:
            allow_whitespace = True
            allow_indent = True
            try:
                from mango_agent.flags import edit_match_mode

                mode = edit_match_mode()
            except Exception:
                mode = str(
                    (__import__("os").environ.get("MANGO_EDIT_MATCH_MODE") or "grounded_ws")
                ).lower()
            allow_fuzzy = mode != "strict_grounded"

    content = file_path.read_text(encoding=encoding)
    updated, replacements, match = apply_replace(
        content,
        old_string,
        new_string,
        replace_all=replace_all,
        allow_fuzzy=allow_fuzzy,
        allow_whitespace=allow_whitespace,
        allow_indent=allow_indent,
    )

    file_path.write_text(updated, encoding=encoding)
    result = file_tool_result(
        file_path,
        _context,
        replacements=replacements,
        bytes_written=len(updated.encode(encoding)),
        match=match,
    )
    if match == "fuzzy":
        result["fuzzy"] = True
    syntax_error = python_syntax_error(file_path, source=updated)
    if syntax_error:
        result["syntax_error"] = syntax_error
    return result
