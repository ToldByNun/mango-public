from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mango_tools.paths import ensure_inside_workspace, file_tool_result, resolve_tool_path
from mango_tools.syntax import python_syntax_error, salvage_python_source

_UNCHANGED = "file unchanged; tests still fail; change the implementation"
_FRAGMENT = re.compile(r"^(?:def|class|import|from)\b.*$", re.DOTALL)
_MARKUP_SUFFIXES = {".html", ".htm", ".css", ".svg", ".xml", ".jsx", ".tsx", ".vue"}
_JUNK_ONLY = re.compile(r"^[\s\"'`\\/<]*$")


def write_file(
    path: str,
    content: str,
    *,
    encoding: str = "utf-8",
    create_dirs: bool = True,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write content to a file, creating parent directories when needed."""
    file_path = resolve_tool_path(path, _context)
    ensure_inside_workspace(file_path, _context, tool="write_file")
    existing = ""
    if file_path.is_file():
        existing = file_path.read_text(encoding=encoding)
        if existing == content:
            raise ValueError(_UNCHANGED)

    if _looks_junk_fragment(content):
        raise ValueError(
            "write_file content is empty/junk (e.g. a lone quote). "
            "File was not changed. Write a COMPLETE file body inside the ``` fence, "
            "or write a short skeleton first then edit_file."
        )

    if file_path.suffix == ".py":
        salvaged = salvage_python_source(content)
        if salvaged is not None:
            content = salvaged
        if _looks_truncated_python(content, existing):
            raise ValueError(
                "write_file content is truncated (incomplete def/class). "
                "File was not changed. Write the COMPLETE module, including the full "
                "function signature and body."
            )
    elif file_path.suffix.lower() in _MARKUP_SUFFIXES:
        if _looks_truncated_markup(content, existing, file_path.suffix.lower()):
            raise ValueError(
                "write_file content looks truncated/incomplete for this HTML/CSS file. "
                "File was not changed. Do NOT rewrite a huge page in one call — "
                "write a short skeleton (<80 lines), then edit_file section by section."
            )

    if create_dirs:
        file_path.parent.mkdir(parents=True, exist_ok=True)

    file_path.write_text(content, encoding=encoding)
    result = file_tool_result(
        file_path,
        _context,
        bytes_written=len(content.encode(encoding)),
        created=True,
    )
    syntax_error = python_syntax_error(file_path, source=content)
    if syntax_error:
        result["syntax_error"] = syntax_error
    return result


def _looks_junk_fragment(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return True
    if len(text) <= 3 and _JUNK_ONLY.match(text):
        return True
    if text in {'"', "'", "`", "``", "```", "</", "<"}:
        return True
    return False


def _looks_truncated_python(content: str, existing: str) -> bool:
    new = (content or "").strip()
    old = (existing or "").strip()
    if not old:
        return False
    if python_syntax_error("new.py", source=content) is None:
        return False
    if len(new) < 24:
        return True
    if new in {"def", "class", "import", "from"}:
        return True
    if _FRAGMENT.fullmatch(new) and "\n" not in new.rstrip() and len(new) < 48:
        return True
    if len(new) < max(24, len(old) // 2) and python_syntax_error("old.py", source=existing) is None:
        return True
    return False


def _looks_truncated_markup(content: str, existing: str, suffix: str) -> bool:
    new = (content or "").strip()
    old = (existing or "").strip()
    if not new:
        return True
    # Shrinking a previously good file to a stub is almost always truncation.
    if old and len(new) < max(40, len(old) // 3):
        return True
    lower = new.lower()
    if suffix in {".html", ".htm"}:
        if "<html" in lower and "</html>" not in lower:
            return True
        if "<body" in lower and "</body>" not in lower:
            return True
        if new.count("<") > new.count(">") + 2:
            return True
        # Opened a tag mid-file with no close and ends abruptly
        if lower.rstrip().endswith(("<", "</", "<div", "<script", "<style", "class=\"", "href=\"")):
            return True
    if suffix == ".css":
        if new.count("{") > new.count("}") + 1:
            return True
    if suffix in {".jsx", ".tsx", ".vue"}:
        if new.count("{") > new.count("}") + 2:
            return True
        if new.count("(") > new.count(")") + 2:
            return True
    return False
