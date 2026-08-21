from __future__ import annotations

from pathlib import Path

from mango_codeintel.types import RefHit, SymbolHit


def snippet_at(root: Path, rel_path: str, line: int, *, radius: int = 1) -> str:
    path = root / rel_path
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if line < 1:
        return ""
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    return "\n".join(lines[start - 1 : end]).strip()


def with_symbol_snippet(root: Path, hit: SymbolHit, *, radius: int = 1) -> SymbolHit:
    return SymbolHit(
        name=hit.name,
        qualname=hit.qualname,
        kind=hit.kind,
        path=hit.path,
        line=hit.line,
        col=hit.col,
        end_line=hit.end_line,
        signature=hit.signature,
        snippet=snippet_at(root, hit.path, hit.line, radius=radius),
    )


def with_ref_snippet(root: Path, hit: RefHit, *, radius: int = 0) -> RefHit:
    return RefHit(
        name=hit.name,
        path=hit.path,
        line=hit.line,
        col=hit.col,
        kind=hit.kind,
        snippet=snippet_at(root, hit.path, hit.line, radius=radius),
    )
