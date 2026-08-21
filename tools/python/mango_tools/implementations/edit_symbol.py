from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mango_tools.paths import resolve_tool_path

_DEF_HEAD = re.compile(r"^\s*(?:async\s+)?def\s+\w+\s*\(|^\s*class\s+\w+", re.M)


def edit_symbol(
    path: str,
    symbol: str,
    body: str,
    *,
    encoding: str = "utf-8",
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace a function/class/method via AST. Neighbors and imports stay put."""
    file_path = resolve_tool_path(path, _context)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    original = file_path.read_text(encoding=encoding)
    prelude, body_for_edit = _split_prelude_and_def(body, symbol.split(".")[-1] if symbol else "")
    try:
        tree = ast.parse(original)
    except SyntaxError as exc:
        raise ValueError(
            f"Cannot edit_symbol {file_path.name}: file has a syntax error "
            f"(line {exc.lineno}). Use write_file to replace the whole file."
        ) from exc

    try:
        target = _resolve_symbol(tree, symbol)
    except ValueError as exc:
        if "not found" in str(exc) and "." not in (symbol or "").strip():
            return _append_new_symbol(file_path, original, symbol, body_for_edit, encoding)
        raise

    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines()
    replacement = _build_replacement(target, lines, body_for_edit)
    start, end = _span(target)
    updated_lines = [*lines[: start - 1], *replacement, *lines[end:]]
    updated = newline.join(updated_lines)
    if original.endswith(("\n", "\r\n")) and not updated.endswith(newline):
        updated += newline
    if prelude:
        updated = _ensure_imports(updated, prelude)

    try:
        ast.parse(updated)
    except SyntaxError as exc:
        raise ValueError(
            f"edit_symbol produced invalid Python for {target.qualname} "
            f"(line {exc.lineno}: {exc.msg}). File was not changed."
        ) from exc

    if updated == original:
        raise ValueError("file unchanged; tests still fail; change the implementation")

    file_path.write_text(updated, encoding=encoding)
    return {
        "path": str(file_path),
        "symbol": target.qualname,
        "kind": target.kind,
        "replaced_lines": [start, end],
        "bytes_written": len(updated.encode(encoding)),
    }


@dataclass
class _Target:
    node: ast.AST
    qualname: str
    kind: str


def _resolve_symbol(tree: ast.AST, symbol: str) -> _Target:
    query = (symbol or "").strip()
    if not query:
        raise ValueError("symbol is required")
    found = _collect_symbols(tree)
    if not found:
        raise ValueError("No functions or classes found in file")

    lowered = query.lower()
    exact = [item for item in found if item.qualname == query or item.node.name == query]
    if not exact:
        exact = [
            item
            for item in found
            if item.qualname.lower() == lowered or item.node.name.lower() == lowered
        ]
    if not exact:
        exact = [item for item in found if item.qualname.lower().endswith("." + lowered)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        names = ", ".join(item.qualname for item in exact)
        raise ValueError(f"Symbol {query!r} is ambiguous; use one of: {names}")
    known = ", ".join(item.qualname for item in found)
    raise ValueError(f"Symbol {query!r} not found. Known: {known}")


def _collect_symbols(tree: ast.AST) -> list[_Target]:
    found: list[_Target] = []

    def visit(node: ast.AST, stack: list[str]) -> None:
        if isinstance(node, ast.ClassDef):
            qual = ".".join([*stack, node.name])
            found.append(_Target(node=node, qualname=qual, kind="class"))
            for child in node.body:
                visit(child, [*stack, node.name])
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = ".".join([*stack, node.name])
            kind = "method" if stack else "function"
            found.append(_Target(node=node, qualname=qual, kind=kind))
            for child in node.body:
                visit(child, [*stack, node.name])

    for child in getattr(tree, "body", []):
        visit(child, [])
    return found


def _span(target: _Target) -> tuple[int, int]:
    node = target.node
    start = int(getattr(node, "lineno", 1) or 1)
    for decorator in getattr(node, "decorator_list", []) or []:
        start = min(start, int(getattr(decorator, "lineno", start) or start))
    end = int(getattr(node, "end_lineno", start) or start)
    return start, end


def _append_new_symbol(
    file_path: Path,
    original: str,
    symbol: str,
    body: str,
    encoding: str,
) -> dict[str, Any]:
    name = (symbol or "").strip()
    text = (body or "").replace("\r\n", "\n").strip("\n")
    if not name or not text.strip():
        raise ValueError("symbol and body are required")
    if _looks_like_definition(text):
        block = textwrap.dedent(text).strip("\n")
    else:
        indented = textwrap.indent(textwrap.dedent(text).strip("\n"), "    ")
        block = f"def {name}(*args, **kwargs):\n{indented}"
    newline = "\r\n" if "\r\n" in original else "\n"
    prefix = original.rstrip("\n")
    updated = prefix + newline + newline + block.replace("\n", newline) + newline
    try:
        ast.parse(updated)
    except SyntaxError as exc:
        raise ValueError(
            f"edit_symbol produced invalid Python for {name} "
            f"(line {exc.lineno}: {exc.msg}). File was not changed."
        ) from exc
    if updated == original:
        raise ValueError("file unchanged; tests still fail; change the implementation")
    file_path.write_text(updated, encoding=encoding)
    kind = "class" if block.lstrip().startswith("class ") else "function"
    return {
        "path": str(file_path),
        "symbol": name,
        "kind": kind,
        "created": True,
        "bytes_written": len(updated.encode(encoding)),
    }


def _build_replacement(target: _Target, lines: list[str], body: str) -> list[str]:
    text = (body or "").replace("\r\n", "\n").strip("\n")
    if not text.strip():
        raise ValueError("body is empty")
    node = target.node
    def_indent = _line_indent(lines, node.lineno)
    if _looks_like_definition(text):
        return _reindent_block(textwrap.dedent(text), def_indent)

    header = _signature_lines(target, lines)
    body_indent = _body_indent(target, lines, def_indent)
    body_lines = _reindent_block(textwrap.dedent(text), body_indent)
    if not body_lines:
        body_lines = [body_indent + "pass"]
    return [*header, *body_lines]


def _split_prelude_and_def(text: str, symbol: str) -> tuple[list[str], str]:
    """Strip leading imports from an edit_symbol body; keep the rest as the edit."""
    raw = (text or "").replace("\r\n", "\n").strip("\n")
    if not raw.strip():
        return [], text or ""
    lines = raw.splitlines()
    prelude: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            prelude.append(stripped)
            index += 1
            continue
        break
    rest = "\n".join(lines[index:]).lstrip("\n")
    if not rest:
        return [], raw
    if _looks_like_definition(rest):
        match = re.match(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", rest)
        name = match.group(1) if match else ""
        want = (symbol or "").strip()
        if want and name and name != want:
            return [], raw
    return prelude, rest


def _ensure_imports(source: str, imports: list[str]) -> str:
    present = {line.strip() for line in source.splitlines() if line.strip().startswith(("import ", "from "))}
    missing = [item for item in imports if item not in present]
    if not missing:
        return source
    newline = "\r\n" if "\r\n" in source else "\n"
    prefix = newline.join(missing) + newline + newline
    return prefix + source


def _looks_like_definition(text: str) -> bool:
    stripped = text.lstrip()
    return bool(_DEF_HEAD.match(stripped))


def _signature_lines(target: _Target, lines: list[str]) -> list[str]:
    node = target.node
    start, _end = _span(target)
    body_start = _body_start_line(node)
    if body_start > node.lineno:
        return lines[start - 1 : body_start - 1]
    header = _same_line_signature(lines[node.lineno - 1])
    prefix: list[str] = []
    if start < node.lineno:
        prefix = lines[start - 1 : node.lineno - 1]
    return [*prefix, header]


def _body_start_line(node: ast.AST) -> int:
    body = getattr(node, "body", None) or []
    if not body:
        return int(getattr(node, "lineno", 1) or 1) + 1
    return int(getattr(body[0], "lineno", node.lineno) or node.lineno)


def _same_line_signature(line: str) -> str:
    depth = 0
    in_str: str | None = None
    escape = False
    for index, char in enumerate(line):
        if in_str:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == in_str:
                in_str = None
            continue
        if char in {'"', "'"}:
            in_str = char
            continue
        if char in "([{":
            depth += 1
            continue
        if char in ")]}":
            depth = max(0, depth - 1)
            continue
        if char == ":" and depth == 0:
            return line[: index + 1].rstrip()
    return line.rstrip()


def _body_indent(target: _Target, lines: list[str], def_indent: str) -> str:
    node = target.node
    body = getattr(node, "body", None) or []
    for stmt in body:
        lineno = int(getattr(stmt, "lineno", 0) or 0)
        if lineno <= node.lineno:
            continue
        indent = _line_indent(lines, lineno)
        if indent:
            return indent
    return def_indent + "    "


def _line_indent(lines: list[str], lineno: int) -> str:
    if not (0 < lineno <= len(lines)):
        return ""
    line = lines[lineno - 1]
    return line[: len(line) - len(line.lstrip(" \t"))]


def _reindent_block(text: str, indent: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            out.append("")
            continue
        out.append(indent + line)
    return out
