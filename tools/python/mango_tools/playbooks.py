"""Procedural playbook vault — \"when X happens, do these steps\".

Replaces repeating login/nav/setup instructions every turn.
Looks in (in order):
  1. MANGO_PLAYBOOKS_DIR
  2. ~/.mango/playbooks
  3. <repo>/playbooks
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_TRIGGERS = re.compile(r"(?im)^triggers:\s*(.+)$")
_NAME = re.compile(r"(?im)^name:\s*(.+)$")
_H1 = re.compile(r"(?m)^#\s+(.+)$")


def _repo_root_guess() -> Path | None:
    env = os.environ.get("MANGO_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "playbooks").is_dir() and (parent / "agent" / "python").is_dir():
            return parent
        if (parent / "runtime" / "config.yaml").is_file() and (parent / "playbooks").is_dir():
            return parent
    return None


def playbook_dirs(repo_root: Path | None = None) -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("MANGO_PLAYBOOKS_DIR", "").strip()
    if env:
        dirs.append(Path(env).expanduser().resolve())
    dirs.append(Path.home() / ".mango" / "playbooks")
    root = repo_root or _repo_root_guess()
    if root is not None:
        dirs.append(root / "playbooks")
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d).lower()
        if key in seen:
            continue
        seen.add(key)
        if d.is_dir():
            out.append(d)
    return out


def _parse_file(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    name = path.stem
    triggers: list[str] = []
    body = text
    fm = _FRONTMATTER.match(text)
    if fm:
        meta = fm.group(1)
        body = text[fm.end() :]
        m_name = _NAME.search(meta)
        if m_name:
            name = m_name.group(1).strip()
        m_trig = _TRIGGERS.search(meta)
        if m_trig:
            triggers = [t.strip().lower() for t in re.split(r"[,|]", m_trig.group(1)) if t.strip()]
    h1 = _H1.search(body)
    title = h1.group(1).strip() if h1 else name
    if not triggers:
        # derive weak triggers from filename + title
        triggers = [w.lower() for w in re.split(r"[-_\s]+", f"{name} {title}") if len(w) > 2]
    return {
        "id": path.stem,
        "name": name,
        "title": title,
        "triggers": triggers,
        "path": str(path),
        "body": body.strip(),
    }


def load_playbooks(repo_root: Path | None = None) -> list[dict[str, Any]]:
    books: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for root in playbook_dirs(repo_root):
        for path in sorted(root.glob("*.md")):
            if path.name.upper() == "README.MD":
                continue
            parsed = _parse_file(path)
            if not parsed:
                continue
            # user dir (~/.mango) wins over repo for same id
            if parsed["id"] in seen_ids:
                continue
            seen_ids.add(parsed["id"])
            books.append(parsed)
    return books


def lookup_playbook(
    query: str,
    *,
    repo_root: Path | None = None,
    limit: int = 2,
) -> dict[str, Any]:
    """Search playbooks by trigger/title/body keywords."""
    q = (query or "").strip().lower()
    if not q:
        return {"ok": False, "error": "empty_query", "playbooks": []}
    terms = [t for t in re.split(r"[\s,;/|]+", q) if t]
    books = load_playbooks(repo_root)
    scored: list[tuple[int, dict[str, Any]]] = []
    for book in books:
        score = 0
        title = str(book["title"]).lower()
        name = str(book["name"]).lower()
        body = str(book["body"]).lower()
        triggers = set(book.get("triggers") or [])
        for term in terms:
            if term in triggers:
                score += 8
            if term in name or term in title:
                score += 5
            if term in body:
                score += min(3, body.count(term))
        if score > 0:
            scored.append((score, book))
    scored.sort(key=lambda x: (-x[0], str(x[1]["title"]).lower()))
    top = [b for _, b in scored[: max(1, min(limit, 4))]]
    if not top:
        available = [f"{b['name']} — {b['title']}" for b in books[:30]]
        return {
            "ok": False,
            "error": "no_match",
            "query": query,
            "available": available,
            "hint": "Add a playbook under ~/.mango/playbooks or repo playbooks/",
        }
    return {
        "ok": True,
        "query": query,
        "playbooks": [
            {
                "name": b["name"],
                "title": b["title"],
                "triggers": b["triggers"],
                "path": b["path"],
                "body": b["body"][:4000],
            }
            for b in top
        ],
    }
