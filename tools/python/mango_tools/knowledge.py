"""Three-tier project knowledge: brief → RAG (FTS) → markdown vault."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_HEADING = re.compile(r"(?m)^(#{1,3})\s+(.+)$")


def _repo_root() -> Path | None:
    env = os.environ.get("MANGO_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "knowledge" / "BRIEF.md").is_file():
            return parent
        if (parent / "runtime" / "config.yaml").is_file() and (parent / "agent" / "python").is_dir():
            return parent
    return None


def knowledge_root(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root() or Path.cwd()
    return root / "knowledge"


def brief_path(repo_root: Path | None = None) -> Path:
    return knowledge_root(repo_root) / "BRIEF.md"


def vault_dir(repo_root: Path | None = None) -> Path:
    return knowledge_root(repo_root) / "vault"


def index_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root() or Path.cwd()
    return root / ".mango" / "knowledge.sqlite"


def read_brief(repo_root: Path | None = None) -> dict[str, Any]:
    path = brief_path(repo_root)
    if not path.is_file():
        return {"ok": False, "error": "brief_missing", "path": str(path)}
    text = path.read_text(encoding="utf-8").strip()
    # Keep response tiny for the model
    if len(text) > 800:
        text = text[:780].rstrip() + "…"
    return {"ok": True, "tier": 1, "path": str(path), "brief": text}


def _normalize_note_key(raw: str) -> str:
    target = raw.split("|", 1)[0].strip()
    target = target.replace("\\", "/").split("/")[-1]
    return re.sub(r"\s+", "-", target).lower().removesuffix(".md")


def list_vault_notes(repo_root: Path | None = None) -> list[dict[str, str]]:
    root = vault_dir(repo_root)
    if not root.is_dir():
        return []
    notes: list[dict[str, str]] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        title = path.stem.replace("-", " ")
        try:
            first = path.read_text(encoding="utf-8").strip().splitlines()
            if first and first[0].startswith("# "):
                title = first[0][2:].strip()
        except OSError:
            pass
        notes.append(
            {
                "id": _normalize_note_key(path.stem),
                "title": title,
                "path": str(path),
                "rel": rel,
            }
        )
    return notes


def open_vault_note(name: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Open a vault note by title, filename, or [[wikilink]] target."""
    key = _normalize_note_key(name or "")
    if not key:
        return {"ok": False, "error": "empty_name"}
    notes = list_vault_notes(repo_root)
    match = None
    for note in notes:
        if note["id"] == key or _normalize_note_key(note["title"]) == key:
            match = note
            break
        if key in note["id"] or key in _normalize_note_key(note["title"]):
            match = note
            break
    if match is None:
        return {
            "ok": False,
            "error": "not_found",
            "query": name,
            "available": [n["title"] for n in notes[:40]],
        }
    path = Path(match["path"])
    body = path.read_text(encoding="utf-8")
    links = sorted({_normalize_note_key(m) for m in _WIKILINK.findall(body)})
    return {
        "ok": True,
        "tier": 3,
        "id": match["id"],
        "title": match["title"],
        "path": match["path"],
        "links": links,
        "body": body[:6000],
    }


def _iter_source_files(repo_root: Path | None = None) -> list[Path]:
    root = repo_root or _repo_root() or Path.cwd()
    files: list[Path] = []
    candidates = [
        knowledge_root(root) / "BRIEF.md",
        vault_dir(root),
        root / "playbooks",
        root / "apps" / "roblox-studio" / "curated",
        Path.home() / ".mango" / "playbooks",
    ]
    for item in candidates:
        if item.is_file() and item.suffix.lower() == ".md":
            files.append(item)
        elif item.is_dir():
            files.extend(sorted(item.rglob("*.md")))
    # de-dupe
    seen: set[str] = set()
    out: list[Path] = []
    for f in files:
        if f.name.upper() == "README.MD":
            continue
        key = str(f.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _chunk_markdown(text: str, *, source: str, max_chars: int = 900) -> list[dict[str, str]]:
    parts = _HEADING.split(text)
    chunks: list[dict[str, str]] = []
    if len(parts) == 1:
        body = text.strip()
        if body:
            chunks.append({"title": Path(source).stem, "body": body[:max_chars], "source": source})
        return chunks
    # parts: [pre, hlevel, title, body, hlevel, title, body, ...]
    pre = parts[0].strip()
    if pre:
        chunks.append({"title": Path(source).stem, "body": pre[:max_chars], "source": source})
    i = 1
    while i + 2 < len(parts):
        title = parts[i + 1].strip()
        body = parts[i + 2].strip()
        i += 3
        if not body and not title:
            continue
        blob = f"# {title}\n{body}".strip()
        if len(blob) <= max_chars:
            chunks.append({"title": title, "body": blob, "source": source})
        else:
            # split long bodies
            start = 0
            while start < len(blob):
                chunks.append(
                    {
                        "title": title,
                        "body": blob[start : start + max_chars],
                        "source": source,
                    }
                )
                start += max_chars
    return chunks


EmbedFn = Callable[[str], list[float] | None]


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            hash TEXT NOT NULL,
            embedding BLOB
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)")
    # FTS — content sync via triggers kept simple: rebuild on refresh
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            title, body, source,
            content='chunks',
            content_rowid='id'
        )
        """
    )
    return conn


def refresh_index(
    repo_root: Path | None = None,
    *,
    embed_fn: EmbedFn | None = None,
) -> dict[str, Any]:
    """Rebuild the knowledge index from markdown sources."""
    db = index_path(repo_root)
    conn = _connect(db)
    files = _iter_source_files(repo_root)
    all_chunks: list[dict[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        all_chunks.extend(_chunk_markdown(text, source=str(path)))

    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM chunks_fts")
    embedded = 0
    for ch in all_chunks:
        h = hashlib.sha256(f"{ch['source']}\0{ch['title']}\0{ch['body']}".encode()).hexdigest()[:16]
        emb_blob = None
        if embed_fn is not None:
            vec = embed_fn(f"{ch['title']}\n{ch['body']}")
            if vec:
                import struct

                emb_blob = struct.pack(f"{len(vec)}f", *vec)
                embedded += 1
        cur = conn.execute(
            "INSERT INTO chunks(source, title, body, hash, embedding) VALUES (?,?,?,?,?)",
            (ch["source"], ch["title"], ch["body"], h, emb_blob),
        )
        rowid = cur.lastrowid
        conn.execute(
            "INSERT INTO chunks_fts(rowid, title, body, source) VALUES (?,?,?,?)",
            (rowid, ch["title"], ch["body"], ch["source"]),
        )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    return {
        "ok": True,
        "path": str(db),
        "files": len(files),
        "chunks": int(n),
        "embedded": embedded,
        "backend": "fts5+optional_embeddings",
    }


def _ensure_index(repo_root: Path | None = None) -> Path:
    db = index_path(repo_root)
    if not db.is_file():
        refresh_index(repo_root)
    return db


def rag_search(
    query: str,
    *,
    repo_root: Path | None = None,
    limit: int = 5,
    refresh: bool = False,
) -> dict[str, Any]:
    """Medium tier: FTS5 search over knowledge chunks (vector hook reserved)."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty_query", "hits": []}
    if refresh:
        refresh_index(repo_root)
    db = _ensure_index(repo_root)
    conn = _connect(db)
    # Simple query sanitize for FTS
    terms = re.findall(r"[A-Za-z0-9_./-]{2,}", q)
    if not terms:
        conn.close()
        return {"ok": False, "error": "no_terms", "hits": []}
    fts_q = " OR ".join(terms[:12])
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.source, c.title, c.body,
                   bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (fts_q, max(1, min(int(limit), 10))),
        ).fetchall()
    except sqlite3.OperationalError:
        # empty index or bad query — rebuild once
        conn.close()
        refresh_index(repo_root)
        conn = _connect(db)
        try:
            rows = conn.execute(
                """
                SELECT c.id, c.source, c.title, c.body,
                       bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_q, max(1, min(int(limit), 10))),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            conn.close()
            return {"ok": False, "error": "fts_error", "detail": str(exc), "hits": []}
    hits = []
    for row in rows:
        hits.append(
            {
                "id": row["id"],
                "title": row["title"],
                "source": row["source"],
                "score": float(row["score"]) if row["score"] is not None else 0.0,
                "snippet": (row["body"] or "")[:700],
            }
        )
    conn.close()
    if not hits:
        return {
            "ok": False,
            "error": "no_hits",
            "query": query,
            "hint": "Try vault_open or project_brief; or refresh the index",
        }
    return {"ok": True, "tier": 2, "query": query, "hits": hits, "backend": "sqlite-fts5"}
