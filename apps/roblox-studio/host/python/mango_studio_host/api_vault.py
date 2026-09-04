"""Roblox API vault — Obsidian-style linked notes for Creator/Luau APIs.

Unlike Python epistemic (importlib introspection), Roblox APIs are looked up
from curated markdown notes under apps/roblox-studio/curated/.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)


def vault_dir(repo_root: Path | None = None) -> Path:
    if repo_root is None:
        # host package → apps/roblox-studio/host/python/mango_studio_host → repo
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "apps" / "roblox-studio" / "curated"
            if candidate.is_dir():
                return candidate
            if (parent / "curated").is_dir() and (parent / "plugin").is_dir():
                return parent / "curated"
        return here.parent.parent.parent / "curated"
    return Path(repo_root) / "apps" / "roblox-studio" / "curated"


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [("vault", text.strip())] if text.strip() else []
    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))
    return sections


def load_vault(repo_root: Path | None = None) -> list[dict[str, str]]:
    """Load all ## sections from curated/*.md as note cards."""
    root = vault_dir(repo_root)
    cards: list[dict[str, str]] = []
    if not root.is_dir():
        return cards
    for path in sorted(root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for title, body in _split_sections(text):
            cards.append(
                {
                    "id": f"{path.stem}/{title}",
                    "title": title,
                    "file": path.name,
                    "body": body,
                }
            )
    return cards


def lookup_api(query: str, *, repo_root: Path | None = None, limit: int = 3) -> dict[str, Any]:
    """Search vault notes by keyword; return top matching cards."""
    q = (query or "").strip().lower()
    if not q:
        return {"ok": False, "error": "empty_query", "cards": []}
    terms = [t for t in re.split(r"[\s,;/|]+", q) if t]
    cards = load_vault(repo_root)
    scored: list[tuple[int, dict[str, str]]] = []
    for card in cards:
        blob = f"{card['title']}\n{card['body']}".lower()
        score = 0
        for term in terms:
            if term in card["title"].lower():
                score += 5
            if term in blob:
                score += blob.count(term)
        if score > 0:
            scored.append((score, card))
    scored.sort(key=lambda x: (-x[0], x[1]["title"].lower()))
    top = [c for _, c in scored[: max(1, min(limit, 5))]]
    if not top:
        # Soft fallback: list available titles so the model can retry
        titles = [c["title"] for c in cards[:40]]
        return {
            "ok": False,
            "error": "no_match",
            "query": query,
            "available": titles,
            "hint": "Retry rbx_api with a title keyword from available",
        }
    return {
        "ok": True,
        "query": query,
        "cards": [
            {
                "title": c["title"],
                "id": c["id"],
                "body": c["body"][:2500],
            }
            for c in top
        ],
    }
