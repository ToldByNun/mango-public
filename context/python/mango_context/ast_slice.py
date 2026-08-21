from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Sequence

DEFAULT_BODY_LINES = 5
MAX_LINE_CHARS = 120
MAX_EXPANDED = 4
_IDENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_STOP = frozenset(
    {
        "if",
        "for",
        "while",
        "return",
        "print",
        "len",
        "str",
        "int",
        "list",
        "dict",
        "range",
        "assert",
        "super",
        "type",
        "set",
        "tuple",
        "bool",
        "float",
        "bytes",
        "and",
        "or",
        "not",
        "in",
        "is",
        "lambda",
        "max",
        "min",
        "sum",
        "open",
        "format",
        "isinstance",
        "enumerate",
        "zip",
        "map",
        "filter",
        "any",
        "all",
        "sorted",
        "abs",
        "round",
        "id",
        "hash",
        "repr",
        "self",
        "cls",
    }
)


def focus_symbols_from_text(*parts: str) -> tuple[str, ...]:
    """Pull callable names out of a goal / verification hint string."""
    seen: set[str] = set()
    names: list[str] = []
    for part in parts:
        for match in _IDENT.finditer(part or ""):
            name = match.group(1)
            key = name.lower()
            if key in _STOP or key in seen:
                continue
            seen.add(key)
            names.append(name)
    return tuple(names)


def slice_source(
    source: str,
    *,
    path: str = "",
    focus_symbols: Sequence[str] = (),
    body_lines: int = DEFAULT_BODY_LINES,
    max_expanded: int = MAX_EXPANDED,
) -> str:
    """Deterministic prompt slice: signature + N body lines, never a raw dump."""
    lines = source.splitlines()
    label = Path(path).name if path else ""
    if _is_python(path, source):
        sliced = _slice_python(
            source,
            lines,
            focus_symbols=focus_symbols,
            body_lines=body_lines,
            max_expanded=max_expanded,
        )
        if sliced:
            header = f"# {label}" if label else ""
            return "\n".join(part for part in (header, sliced) if part)
    return _head_slice(lines, path=label, body_lines=body_lines)


def _is_python(path: str, source: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    if lowered.endswith(".py"):
        return True
    stripped = source.lstrip()
    return stripped.startswith(("def ", "class ", "async def ", "import ", "from "))


def _slice_python(
    source: str,
    lines: list[str],
    *,
    focus_symbols: Sequence[str],
    body_lines: int,
    max_expanded: int,
) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    focus = {name.lower() for name in focus_symbols if name}
    imports = _import_names(tree)
    top_defs = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    chunks: list[str] = []
    if imports:
        chunks.append("imports: " + ", ".join(imports[:10]))

    expanded = 0
    for node in top_defs:
        name = node.name
        wanted = name.lower() in focus
        if not wanted and not focus and expanded < max_expanded:
            wanted = True
            expanded += 1
        chunks.append(
            _render_node(node, lines, expand=wanted, body_lines=body_lines, focus=focus)
        )

    if not chunks:
        return ""
    return "\n".join(chunks)


def _import_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or "."
            imported = ", ".join(alias.name for alias in node.names[:4])
            names.append(f"{module}({imported})" if imported else module)
    return names


def _render_node(
    node: ast.AST,
    lines: list[str],
    *,
    expand: bool,
    body_lines: int,
    focus: set[str],
) -> str:
    if isinstance(node, ast.ClassDef):
        return _render_class(node, lines, expand=expand, body_lines=body_lines, focus=focus)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _render_function(node, lines, expand=expand, body_lines=body_lines)
    return ""


def _render_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
    *,
    expand: bool,
    body_lines: int,
) -> str:
    start = node.lineno
    end = getattr(node, "end_lineno", start) or start
    total = max(0, end - start)
    sig = _clip_line(_signature_line(node, lines))
    if not expand:
        return f"{sig} ... ({total} more lines)" if total else sig
    body_start = node.body[0].lineno if node.body else start + 1
    shown = _take_lines(lines, start, min(end, body_start + body_lines - 1))
    rest = end - (body_start + body_lines - 1)
    if rest > 0:
        shown.append(f"... ({rest} more lines)")
    return "\n".join(shown) if shown else sig


def _render_class(
    node: ast.ClassDef,
    lines: list[str],
    *,
    expand: bool,
    body_lines: int,
    focus: set[str],
) -> str:
    start = node.lineno
    end = getattr(node, "end_lineno", start) or start
    total = max(0, end - start)
    header = _clip_line(lines[start - 1].rstrip() if 0 < start <= len(lines) else f"class {node.name}:")
    methods = [
        child
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if not expand:
        bits = [f"{header} ... ({total} more lines)"]
        for method in methods[:6]:
            bits.append("    " + _clip_line(_signature_line(method, lines)) + " ...")
        return "\n".join(bits)
    chunks = [header]
    for method in methods:
        wanted = method.name.lower() in focus or expand
        rendered = _render_function(method, lines, expand=wanted, body_lines=body_lines)
        chunks.append(_indent(rendered, 4))
    if not methods:
        shown = _take_lines(lines, start, min(end, start + body_lines))
        rest = end - (start + body_lines)
        chunks = shown
        if rest > 0:
            chunks.append(f"... ({rest} more lines)")
    return "\n".join(chunks)


def _signature_line(node: ast.AST, lines: list[str]) -> str:
    lineno = getattr(node, "lineno", 1)
    if 0 < lineno <= len(lines):
        return lines[lineno - 1].rstrip()
    name = getattr(node, "name", "symbol")
    return f"def {name}(...):"


def _take_lines(lines: list[str], start: int, end: int) -> list[str]:
    out: list[str] = []
    for index in range(max(1, start), min(len(lines), end) + 1):
        out.append(_clip_line(lines[index - 1].rstrip()))
    return out


def _head_slice(lines: list[str], *, path: str, body_lines: int) -> str:
    keep = max(1, body_lines)
    shown = [_clip_line(line.rstrip()) for line in lines[:keep]]
    rest = len(lines) - keep
    if path:
        shown.insert(0, f"# {path} ({len(lines)} lines)")
    elif rest > 0:
        shown.insert(0, f"# ({len(lines)} lines)")
    if rest > 0:
        shown.append(f"... ({rest} more lines)")
    return "\n".join(shown)


def _clip_line(line: str, limit: int = MAX_LINE_CHARS) -> str:
    if len(line) <= limit:
        return line
    return line[: limit - 3] + "..."


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())
