from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mango_tools.paths import resolve_tool_path

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mango",
    ".devdeck",
}

DEFAULT_GLOB = "**/*"


def search_code(
    pattern: str,
    path: str = ".",
    *,
    case_insensitive: bool = False,
    max_results: int = 50,
    include_glob: str = DEFAULT_GLOB,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Simple grep-style search across files under `path`."""
    root = resolve_tool_path(path, _context)
    if not root.exists():
        raise FileNotFoundError(f"Search path not found: {root}")

    flags = re.IGNORECASE if case_insensitive else 0
    regex = re.compile(pattern, flags)

    matches: list[dict[str, Any]] = []
    truncated = False

    for file_path in _iter_files(root, include_glob):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            if not regex.search(line):
                continue
            matches.append(
                {
                    "path": str(file_path),
                    "line": line_no,
                    "text": line.rstrip("\n"),
                }
            )
            if len(matches) >= max_results:
                truncated = True
                break
        if truncated:
            break

    return {
        "pattern": pattern,
        "root": str(root),
        "match_count": len(matches),
        "truncated": truncated,
        "matches": matches,
    }


def _iter_files(root: Path, include_glob: str):
    if root.is_file():
        yield root
        return

    for file_path in root.glob(include_glob):
        if not file_path.is_file():
            continue
        if any(part in DEFAULT_IGNORE_DIRS for part in file_path.parts):
            continue
        yield file_path
