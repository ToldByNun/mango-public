from __future__ import annotations

import json
import re
from typing import Any

from mango_codeintel.indexer import CodeIndexer
from mango_codeintel.snippet_provider import with_ref_snippet, with_symbol_snippet
from mango_codeintel.types import FileHit, GitSnapshot, RefHit, SymbolHit

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_REF_HINTS = ("call", "called", "aufruf", "aufgerufen", "used", "usage", "reference", "referenz")
# Word-ish phrases only — bare "defin" matches "definitions" in NL questions and
# forces definition mode with no symbol → empty result (agent lookup loops).
_DEF_HINTS = ("where is", "wo ist", "wo wird", "signature of", "signatur von", "defined in")
_IMPACT_HINTS = ("impact", "abhängig", "affects", "depends", "dependency", "repo map", "who imports")
_TEST_FILE = re.compile(r"(?:^|/)tests?(?:/|$)|(?:^|/)test_[^/]+\.py$|_test\.py$")


class CodeQuery:
    def __init__(self, indexer: CodeIndexer) -> None:
        self.indexer = indexer
        self.root = indexer.root
        self.store = indexer.store

    def get_symbol_definition(self, symbol_name: str) -> list[SymbolHit]:
        hits = [_symbol_from_row(row) for row in self.store.symbols_named(symbol_name)]
        return [with_symbol_snippet(self.root, hit) for hit in hits]

    def get_references(self, symbol_name: str) -> list[RefHit]:
        hits = [_ref_from_row(row) for row in self.store.refs_named(symbol_name)]
        return [with_ref_snippet(self.root, hit) for hit in hits]

    def get_relevant_files(self, task_description: str, *, limit: int = 10) -> list[FileHit]:
        tokens = [token.lower() for token in _IDENT.findall(task_description) if len(token) > 1]
        ranked = self.store.search_files(tokens, limit=limit)
        return [FileHit(path=path, score=score, reasons=reasons) for path, score, reasons in ranked]

    def git_status(self) -> GitSnapshot:
        raw = self.store.get_meta("git")
        if not raw:
            return GitSnapshot()
        data = json.loads(raw)
        return GitSnapshot(
            branch=data.get("branch", ""),
            changed_files=list(data.get("changed_files") or []),
            recent_commits=list(data.get("recent_commits") or []),
            available=bool(data.get("available")),
        )

    def impact(self, *, symbol: str | None = None, path: str | None = None, limit: int = 8) -> dict[str, Any]:
        """Compact dependency neighborhood: defs, importers, call sites, related tests."""
        def_files: list[str] = []
        signatures: list[str] = []
        dependent: list[str] = []
        rel = (path or "").replace("\\", "/")

        if symbol:
            for row in self.store.symbols_named(symbol):
                hit_path = str(row["path"])
                if hit_path not in def_files:
                    def_files.append(hit_path)
                sig = str(row["signature"] or "")
                if sig and sig not in signatures:
                    signatures.append(sig)
            for row in self.store.refs_named(symbol):
                dependent.append(str(row["path"]))

        seed_paths = [p for p in ([rel] if rel else []) + def_files if p]
        for seed in seed_paths:
            dependent.extend(self.store.importers_of(seed))
            if not symbol:
                for row in self.store.symbols_in_file(seed)[:24]:
                    for ref in self.store.refs_named(str(row["name"])):
                        dependent.append(str(ref["path"]))

        def_set = set(def_files) | set(seed_paths)
        unique_deps: list[str] = []
        for item in dependent:
            if item in unique_deps or item in def_set:
                continue
            unique_deps.append(item)
        tests = [item for item in unique_deps if _is_test_file(item)]
        others = [item for item in unique_deps if item not in tests]
        return {
            "symbol": symbol,
            "path": rel or None,
            "definition_files": def_files[:limit],
            "signatures": signatures[:limit],
            "dependent_files": others[:limit],
            "test_files": tests[:limit],
        }

    def lookup(self, query: str, *, kind: str = "auto") -> dict[str, Any]:
        """Unified query used by the codebase_lookup tool."""
        lowered = query.lower()
        symbol = _pick_symbol(query, self.store.all_symbol_names())
        mode = kind if kind != "auto" else _infer_kind(lowered)

        result: dict[str, Any] = {"query": query, "kind": mode, "symbol": symbol}
        if mode in {"definition", "auto"} and symbol:
            result["definitions"] = [hit.to_dict() for hit in self.get_symbol_definition(symbol)]
        if mode in {"references", "auto"} and symbol:
            refs = self.get_references(symbol)
            if mode == "auto" and _wants_references(lowered):
                result["kind"] = "references"
            result["references"] = [hit.to_dict() for hit in refs]
        # Always fall back to file search when no symbol matched — otherwise
        # definition/references mode returns success with empty lists and the
        # agent loops on the same NL query.
        need_files = (
            mode == "files"
            or not symbol
            or (mode == "auto" and "files" not in result)
            or (
                mode in {"definition", "references"}
                and not (result.get("definitions") or result.get("references"))
            )
        )
        if need_files:
            result["files"] = [hit.to_dict() for hit in self.get_relevant_files(query)]
            if not symbol and mode in {"definition", "references"} and result["files"]:
                result["kind"] = "files"
                result["note"] = (
                    f"no indexed symbol for this query; fell back to file search "
                    f"({len(result['files'])} hits)"
                )
            elif not symbol and not result["files"]:
                result["note"] = "no symbol or file hits — try search_code / list_dir / glob_files"
        path_hint = _pick_path(query) if (mode == "impact" and not symbol) else None
        if mode == "impact" or symbol or path_hint:
            if mode == "impact":
                result["kind"] = "impact"
            payload = self.impact(symbol=symbol, path=path_hint)
            if payload.get("dependent_files") or payload.get("test_files") or mode == "impact":
                result["impact"] = payload
        result["git"] = self.git_status().to_dict()
        return result


def _infer_kind(lowered: str) -> str:
    if any(hint in lowered for hint in _IMPACT_HINTS):
        return "impact"
    if any(hint in lowered for hint in _REF_HINTS):
        return "references"
    if any(hint in lowered for hint in _DEF_HINTS):
        return "definition"
    return "auto"


def _wants_references(lowered: str) -> bool:
    return any(hint in lowered for hint in _REF_HINTS)


def _pick_path(query: str) -> str | None:
    match = re.search(r"([A-Za-z0-9_./\\-]+\.py)", query)
    if not match:
        return None
    return match.group(1).replace("\\", "/")


def _is_test_file(path: str) -> bool:
    posix = path.replace("\\", "/")
    return bool(_TEST_FILE.search(posix))


def _pick_symbol(query: str, known: list[str]) -> str | None:
    quoted = re.findall(r"['\"`]([A-Za-z_][A-Za-z0-9_]*)['\"`]", query)
    tokens = _IDENT.findall(query)
    known_set = set(known)
    for candidate in [*quoted, *reversed(tokens)]:
        if candidate in known_set:
            return candidate
    for token in reversed(tokens):
        if token.lower() not in {"wo", "wird", "funktion", "function", "where", "is", "the", "called", "aufruf"}:
            if token in known_set or quoted:
                return token if token in known_set else (quoted[0] if quoted else None)
    return quoted[0] if quoted else None


def _symbol_from_row(row: Any) -> SymbolHit:
    return SymbolHit(
        name=str(row["name"]),
        qualname=str(row["qualname"]),
        kind=str(row["kind"]),
        path=str(row["path"]),
        line=int(row["line"]),
        col=int(row["col"]),
        end_line=int(row["end_line"]),
        signature=str(row["signature"] or ""),
    )


def _ref_from_row(row: Any) -> RefHit:
    return RefHit(
        name=str(row["name"]),
        path=str(row["path"]),
        line=int(row["line"]),
        col=int(row["col"]),
        kind=str(row["kind"]),
    )
