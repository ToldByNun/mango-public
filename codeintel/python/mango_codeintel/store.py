from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    sha1 TEXT NOT NULL,
    language TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER NOT NULL,
    col INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    signature TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS refs (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    line INTEGER NOT NULL,
    col INTEGER NOT NULL,
    kind TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    names TEXT NOT NULL DEFAULT '[]',
    resolved_path TEXT,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qual ON symbols(qualname);
CREATE INDEX IF NOT EXISTS idx_refs_name ON refs(name);
CREATE INDEX IF NOT EXISTS idx_imports_resolved ON imports(resolved_path);
"""


class IndexStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def file_row(self, rel_path: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM files WHERE path = ?", (rel_path,)).fetchone()

    def upsert_file(self, rel_path: str, mtime: float, size: int, sha1: str, language: str) -> int:
        existing = self.file_row(rel_path)
        if existing is None:
            cur = self._conn.execute(
                "INSERT INTO files(path, mtime, size, sha1, language) VALUES (?, ?, ?, ?, ?)",
                (rel_path, mtime, size, sha1, language),
            )
            return int(cur.lastrowid)
        file_id = int(existing["id"])
        self._conn.execute(
            "UPDATE files SET mtime = ?, size = ?, sha1 = ?, language = ? WHERE id = ?",
            (mtime, size, sha1, language, file_id),
        )
        return file_id

    def delete_file(self, rel_path: str) -> None:
        self._conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))

    def clear_file_payload(self, file_id: int) -> None:
        self._conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
        self._conn.execute("DELETE FROM refs WHERE file_id = ?", (file_id,))
        self._conn.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))

    def insert_symbol(
        self,
        file_id: int,
        *,
        name: str,
        qualname: str,
        kind: str,
        line: int,
        col: int,
        end_line: int,
        signature: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO symbols(file_id, name, qualname, kind, line, col, end_line, signature) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, name, qualname, kind, line, col, end_line, signature),
        )

    def insert_ref(self, file_id: int, *, name: str, line: int, col: int, kind: str) -> None:
        self._conn.execute(
            "INSERT INTO refs(file_id, name, line, col, kind) VALUES (?, ?, ?, ?, ?)",
            (file_id, name, line, col, kind),
        )

    def insert_import(
        self,
        file_id: int,
        *,
        module: str,
        names: list[str],
        resolved_path: str | None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO imports(file_id, module, names, resolved_path) VALUES (?, ?, ?, ?)",
            (file_id, module, json.dumps(names), resolved_path),
        )

    def listed_paths(self) -> set[str]:
        rows = self._conn.execute("SELECT path FROM files").fetchall()
        return {str(row["path"]) for row in rows}

    def symbols_named(self, name: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT s.*, f.path FROM symbols s JOIN files f ON f.id = s.file_id "
                "WHERE s.name = ? OR s.qualname = ? OR s.qualname LIKE ? "
                "ORDER BY f.path, s.line",
                (name, name, f"%.{name}"),
            )
        )

    def refs_named(self, name: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT r.*, f.path FROM refs r JOIN files f ON f.id = r.file_id "
                "WHERE r.name = ? OR r.name LIKE ? ORDER BY f.path, r.line",
                (name, f"%.{name}"),
            )
        )

    def search_files(self, tokens: list[str], limit: int = 20) -> list[tuple[str, int, list[str]]]:
        scores: dict[str, tuple[int, list[str]]] = {}
        for token in tokens:
            like = f"%{token}%"
            for row in self._conn.execute("SELECT path FROM files WHERE path LIKE ?", (like,)):
                path = str(row["path"])
                score, reasons = scores.get(path, (0, []))
                scores[path] = (score + 3, reasons + [f"path:{token}"])
            for row in self._conn.execute(
                "SELECT f.path, s.name, s.qualname FROM symbols s JOIN files f ON f.id = s.file_id "
                "WHERE s.name LIKE ? OR s.qualname LIKE ?",
                (like, like),
            ):
                path = str(row["path"])
                score, reasons = scores.get(path, (0, []))
                label = str(row["qualname"] or row["name"])
                scores[path] = (score + 5, reasons + [f"symbol:{label}"])
        ranked = sorted(scores.items(), key=lambda item: (-item[1][0], item[0]))
        return [(path, data[0], data[1][:6]) for path, data in ranked[:limit]]

    def all_symbol_names(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT name FROM symbols").fetchall()
        return [str(row["name"]) for row in rows]

    def symbols_in_file(self, rel_path: str) -> list[sqlite3.Row]:
        posix = rel_path.replace("\\", "/")
        return list(
            self._conn.execute(
                "SELECT s.*, f.path FROM symbols s JOIN files f ON f.id = s.file_id "
                "WHERE f.path = ? ORDER BY s.line",
                (posix,),
            )
        )

    def importers_of(self, rel_path: str) -> list[str]:
        posix = rel_path.replace("\\", "/").lstrip("./")
        rows = self._conn.execute(
            "SELECT DISTINCT f.path FROM imports i JOIN files f ON f.id = i.file_id "
            "WHERE i.resolved_path = ? OR i.resolved_path LIKE ?",
            (posix, f"%/{posix}"),
        )
        return [str(row["path"]) for row in rows]

    def commit(self) -> None:
        self._conn.commit()
