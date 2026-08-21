from __future__ import annotations

from pathlib import Path
from typing import Sequence

from mango_codeintel.adapters.python_ast import parse_python

DEFAULT_BODY_LINES = 5
MAX_LINE_CHARS = 120
MAX_EXPANDED = 4


def slice_source(
    source: str,
    *,
    path: str = "",
    focus_symbols: Sequence[str] = (),
    body_lines: int = DEFAULT_BODY_LINES,
    max_expanded: int = MAX_EXPANDED,
) -> str:
    """AST slice for a source string: signature + N body lines."""
    try:
        from mango_context.ast_slice import slice_source as impl
    except ImportError:
        impl = _slice_with_index_parser
    return impl(
        source,
        path=path,
        focus_symbols=focus_symbols,
        body_lines=body_lines,
        max_expanded=max_expanded,
    )


def slice_file(
    root: str | Path,
    path: str | Path,
    *,
    focus_symbols: Sequence[str] = (),
    body_lines: int = DEFAULT_BODY_LINES,
) -> str:
    """Read a repo file and return an AST-first prompt slice."""
    root_path = Path(root)
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = root_path / file_path
    if not file_path.is_file():
        return ""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    rel = str(file_path)
    try:
        rel = str(file_path.relative_to(root_path))
    except ValueError:
        pass
    return slice_source(source, path=rel, focus_symbols=focus_symbols, body_lines=body_lines)


def _slice_with_index_parser(
    source: str,
    *,
    path: str = "",
    focus_symbols: Sequence[str] = (),
    body_lines: int = DEFAULT_BODY_LINES,
    max_expanded: int = MAX_EXPANDED,
) -> str:
    lines = source.splitlines()
    rel = path.replace("\\", "/") or "module.py"
    parsed = parse_python(source, rel_path=Path(rel).name, root=Path("."))
    label = Path(path).name if path else ""
    if not parsed.symbols:
        keep = max(1, body_lines)
        shown = [_clip(line) for line in lines[:keep]]
        rest = len(lines) - keep
        if label:
            shown.insert(0, f"# {label} ({len(lines)} lines)")
        if rest > 0:
            shown.append(f"... ({rest} more lines)")
        return "\n".join(shown)

    focus = {name.lower() for name in focus_symbols if name}
    chunks: list[str] = []
    if label:
        chunks.append(f"# {label}")
    imports = [item.module for item in parsed.imports[:8] if item.module]
    if imports:
        chunks.append("imports: " + ", ".join(imports))

    top = [sym for sym in parsed.symbols if "." not in sym.qualname]
    expanded = 0
    for sym in top:
        wanted = sym.name.lower() in focus
        if not wanted and not focus and expanded < max_expanded:
            wanted = True
            expanded += 1
        chunks.append(_render_symbol(lines, sym, expand=wanted, body_lines=body_lines))
    return "\n".join(chunks)


def _render_symbol(lines: list[str], sym: object, *, expand: bool, body_lines: int) -> str:
    start = int(getattr(sym, "line", 1) or 1)
    end = int(getattr(sym, "end_line", start) or start)
    total = max(0, end - start)
    sig = _clip(_line(lines, start) or str(getattr(sym, "signature", "") or ""))
    if not expand:
        return f"{sig} ... ({total} more lines)" if total else sig
    shown = [_clip(_line(lines, index)) for index in range(start, min(end, start + body_lines) + 1)]
    shown = [line for line in shown if line is not None]
    rest = end - (start + body_lines)
    if rest > 0:
        shown.append(f"... ({rest} more lines)")
    return "\n".join(shown) if shown else sig


def _line(lines: list[str], lineno: int) -> str:
    if 0 < lineno <= len(lines):
        return lines[lineno - 1].rstrip()
    return ""


def _clip(line: str, limit: int = MAX_LINE_CHARS) -> str:
    if len(line) <= limit:
        return line
    return line[: limit - 3] + "..."
