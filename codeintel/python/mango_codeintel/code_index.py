from __future__ import annotations

from pathlib import Path
from typing import Any

from mango_codeintel.indexer import CodeIndexer
from mango_codeintel.query import CodeQuery


class CodeIndex:
    """Facade: index a repo and answer symbol/file queries."""

    def __init__(self, root: str | Path, *, db_path: str | Path | None = None) -> None:
        self.indexer = CodeIndexer(root, db_path=db_path)
        self.query = CodeQuery(self.indexer)

    @property
    def root(self) -> Path:
        return self.indexer.root

    def refresh(self, *, force: bool = False) -> dict:
        return self.indexer.refresh(force=force)

    def get_symbol_definition(self, symbol_name: str):
        self.refresh()
        return self.query.get_symbol_definition(symbol_name)

    def get_references(self, symbol_name: str):
        self.refresh()
        return self.query.get_references(symbol_name)

    def get_relevant_files(self, task_description: str):
        self.refresh()
        return self.query.get_relevant_files(task_description)

    def slice_source(
        self,
        source: str,
        *,
        path: str = "",
        focus_symbols: tuple[str, ...] | list[str] = (),
        body_lines: int = 5,
    ) -> str:
        from mango_codeintel.slice import slice_source

        return slice_source(source, path=path, focus_symbols=focus_symbols, body_lines=body_lines)

    def slice_file(
        self,
        path: str | Path,
        *,
        focus_symbols: tuple[str, ...] | list[str] = (),
        body_lines: int = 5,
    ) -> str:
        from mango_codeintel.slice import slice_file

        return slice_file(self.root, path, focus_symbols=focus_symbols, body_lines=body_lines)

    def impact(self, *, symbol: str | None = None, path: str | None = None) -> dict[str, Any]:
        self.refresh()
        return self.query.impact(symbol=symbol, path=path)

    def lookup(self, query: str, *, kind: str = "auto") -> dict[str, Any]:
        self.refresh()
        return self.query.lookup(query, kind=kind)


def register_codebase_lookup(
    registry: Any,
    root: str | Path,
    *,
    index: CodeIndex | None = None,
) -> CodeIndex:
    code_index = index or CodeIndex(root)

    def codebase_lookup(query: str, kind: str = "auto", _context: dict | None = None) -> dict[str, Any]:
        return code_index.lookup(query, kind=kind)

    if not registry.has("codebase_lookup"):
        registry.register(
            "codebase_lookup",
            codebase_lookup,
            description="Query the indexed codebase for symbol definitions, references, impact (who uses X), and relevant files.",
            parameters={
                "query": {"type": "string", "description": "Natural-language or symbol query"},
                "kind": {
                    "type": "string",
                    "description": "auto | definition | references | files | impact",
                    "default": "auto",
                },
            },
            required=["query"],
        )
    return code_index
