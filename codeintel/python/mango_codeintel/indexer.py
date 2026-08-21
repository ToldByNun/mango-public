from __future__ import annotations

import hashlib
import json
import sys
import warnings
from pathlib import Path

from mango_codeintel.adapters.python_ast import parse_python
from mango_codeintel.git_status import git_snapshot
from mango_codeintel.store import IndexStore

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mango",
    ".devdeck",  # legacy cache dir name
    ".pytest_cache",
    "dist",
    "build",
    "docs",
    "doc",
    "examples",
    "benchmarks",
    "asv_bench",
    "site-packages",
    "htmlcov",
    ".tox",
    "vendor",
    "third_party",
}

INDEXABLE_LANGS = {".py": "python"}


class CodeIndexer:
    def __init__(self, root: str | Path, *, db_path: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            mango_db = self.root / ".mango" / "codeintel.sqlite"
            legacy_db = self.root / ".devdeck" / "codeintel.sqlite"
            self.db_path = mango_db if mango_db.is_file() or not legacy_db.is_file() else legacy_db
        self.store = IndexStore(self.db_path)

    def refresh(self, *, force: bool = False) -> dict:
        """Full scan on first run; afterwards only reparse changed/new/deleted files."""
        current: dict[str, Path] = {}
        for path in self.root.rglob("*.py"):
            if not path.is_file():
                continue
            parts = path.relative_to(self.root).parts
            if any(part in IGNORE_DIRS for part in parts):
                continue
            # Vendored copies (e.g. requests/packages/urllib3) spam SyntaxWarning and bloat the index.
            if "packages" in parts[:-1]:
                continue
            current[path.relative_to(self.root).as_posix()] = path
        known = self.store.listed_paths()

        for rel in known - set(current):
            self.store.delete_file(rel)

        parsed = 0
        skipped = 0
        if (force or not known) and len(current) >= 50:
            print(
                f"[mango] codeintel indexing {len(current)} python files ...",
                file=sys.stderr,
                flush=True,
            )
        for rel, path in current.items():
            stat = path.stat()
            digest = _sha1(path)
            language = INDEXABLE_LANGS.get(path.suffix.lower(), "other")
            existing = None if force else self.store.file_row(rel)
            unchanged = (
                existing is not None
                and float(existing["mtime"]) == stat.st_mtime
                and int(existing["size"]) == stat.st_size
                and str(existing["sha1"]) == digest
            )
            if unchanged:
                skipped += 1
                continue
            file_id = self.store.upsert_file(rel, stat.st_mtime, stat.st_size, digest, language)
            self.store.clear_file_payload(file_id)
            if language == "python":
                source = path.read_text(encoding="utf-8", errors="replace")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    result = parse_python(source, rel_path=rel, root=self.root)
                for symbol in result.symbols:
                    self.store.insert_symbol(
                        file_id,
                        name=symbol.name,
                        qualname=symbol.qualname,
                        kind=symbol.kind,
                        line=symbol.line,
                        col=symbol.col,
                        end_line=symbol.end_line,
                        signature=symbol.signature,
                    )
                for ref in result.refs:
                    self.store.insert_ref(file_id, name=ref.name, line=ref.line, col=ref.col, kind=ref.kind)
                for imp in result.imports:
                    self.store.insert_import(
                        file_id,
                        module=imp.module,
                        names=imp.names,
                        resolved_path=imp.resolved_path,
                    )
            parsed += 1

        git = git_snapshot(self.root)
        self.store.set_meta("git", json.dumps(git.to_dict()))
        self.store.set_meta("root", str(self.root))
        self.store.commit()
        if parsed:
            print(
                f"[mango] codeintel indexed {parsed} files ({skipped} unchanged, {len(current)} total)",
                file=sys.stderr,
                flush=True,
            )
        return {"parsed": parsed, "skipped": skipped, "files": len(current), "git": git.to_dict()}


def _sha1(path: Path) -> str:
    hasher = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(64 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
