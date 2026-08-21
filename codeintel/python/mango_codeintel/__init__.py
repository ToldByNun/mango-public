"""Mango CodeIntel — indexed codebase analysis (AST + SQLite)."""

from mango_codeintel.code_index import CodeIndex, register_codebase_lookup
from mango_codeintel.query import CodeQuery
from mango_codeintel.slice import slice_file, slice_source
from mango_codeintel.types import FileHit, GitSnapshot, RefHit, SymbolHit

__all__ = [
    "CodeIndex",
    "CodeQuery",
    "FileHit",
    "GitSnapshot",
    "RefHit",
    "SymbolHit",
    "register_codebase_lookup",
    "slice_file",
    "slice_source",
]
