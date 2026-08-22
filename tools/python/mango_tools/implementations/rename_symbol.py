from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path
from typing import Any

from mango_tools.paths import ensure_inside_workspace, resolve_tool_path

_SKIP_DIR_NAMES = {".git", ".venv", "venv", "__pycache__", "node_modules", ".tox", ".mango", ".devdeck"}
_UNCHANGED = "file unchanged; tests still fail; change the implementation"


def rename_symbol(
    old_name: str,
    new_name: str,
    *,
    path: str = ".",
    encoding: str = "utf-8",
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """AST/tokenize rename of a Python identifier across a file or workspace."""
    old = (old_name or "").strip()
    new = (new_name or "").strip()
    if not old.isidentifier() or not new.isidentifier():
        raise ValueError("old_name and new_name must be valid identifiers")
    if old == new:
        raise ValueError(_UNCHANGED)

    if not path or path == ".":
        workspace = (_context or {}).get("workspace")
        if workspace:
            path = str(workspace)

    root = resolve_tool_path(path, _context)
    ensure_inside_workspace(root, _context, tool="rename_symbol")
    files = _python_files(root)
    if not files:
        raise FileNotFoundError(f"No Python files under {root}")

    changed: list[dict[str, Any]] = []
    for file_path in files:
        original = file_path.read_text(encoding=encoding)
        updated, count = _rename_identifiers(original, old, new)
        if count == 0 or updated == original:
            continue
        try:
            ast.parse(updated)
        except SyntaxError as exc:
            raise ValueError(
                f"rename_symbol produced invalid Python in {file_path.name} "
                f"(line {exc.lineno}: {exc.msg}). Files were not changed."
            ) from exc
        file_path.write_text(updated, encoding=encoding)
        changed.append({"path": str(file_path), "replacements": count})

    if not changed:
        raise ValueError(f"{_UNCHANGED} (no references to {old!r})")
    return {"old_name": old, "new_name": new, "files": changed}


def _python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    found: list[Path] = []
    for path in root.rglob("*.py"):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            rel_parts = path.parts
        if any(part in _SKIP_DIR_NAMES for part in rel_parts[:-1]):
            continue
        found.append(path)
    return sorted(found)


def _rename_identifiers(source: str, old: str, new: str) -> tuple[str, int]:
    reader = io.StringIO(source)
    try:
        tokens = list(tokenize.generate_tokens(reader.readline))
    except tokenize.TokenError:
        return source, 0
    modules = _imported_module_names(tokens)
    spans: list[tuple[int, int]] = []
    for index, tok in enumerate(tokens):
        if tok.type != tokenize.NAME or tok.string != old:
            continue
        if tok.string in modules:
            continue
        if _is_module_after_import(tokens, index):
            continue
        start = _offset(source, tok.start)
        end = _offset(source, tok.end)
        if start is None or end is None:
            continue
        spans.append((start, end))
    if not spans:
        return source, 0
    updated = source
    for start, end in reversed(spans):
        updated = updated[:start] + new + updated[end:]
    return updated, len(spans)


def _imported_module_names(tokens: list[tokenize.TokenInfo]) -> set[str]:
    names: set[str] = set()
    for index, tok in enumerate(tokens):
        if tok.string != "import":
            continue
        if _is_from_import(tokens, index):
            continue
        next_i = _next_code_index(tokens, index)
        if next_i is not None and tokens[next_i].type == tokenize.NAME:
            names.add(tokens[next_i].string)
    return names


def _next_code_index(tokens: list[tokenize.TokenInfo], index: int) -> int | None:
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT}
    for pos in range(index + 1, len(tokens)):
        if tokens[pos].type in skip:
            continue
        return pos
    return None


def _is_from_import(tokens: list[tokenize.TokenInfo], import_index: int) -> bool:
    prev = _prev_code_index(tokens, import_index)
    while prev is not None and tokens[prev].string not in {"from", "import"} and (
        tokens[prev].type == tokenize.NAME or tokens[prev].string in {".", ","}
    ):
        prev = _prev_code_index(tokens, prev)
    return prev is not None and tokens[prev].string == "from"


def _is_module_after_import(tokens: list[tokenize.TokenInfo], index: int) -> bool:
    prev_i = _prev_code_index(tokens, index)
    if prev_i is None or tokens[prev_i].string != "import":
        return False
    return not _is_from_import(tokens, prev_i)


def _prev_code_index(tokens: list[tokenize.TokenInfo], index: int) -> int | None:
    for pos in range(index - 1, -1, -1):
        tok = tokens[pos]
        if tok.type in {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT}:
            continue
        return pos
    return None


def _offset(source: str, pos: tuple[int, int]) -> int | None:
    line, col = pos
    lines = source.splitlines(keepends=True)
    if not (1 <= line <= len(lines) + 1):
        return None
    return sum(len(item) for item in lines[: line - 1]) + col
