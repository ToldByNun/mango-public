"""rbx_api — look up Roblox/Luau API notes from the curated vault."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def rbx_api(
    query: str,
    *,
    limit: int = 3,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search the Roblox API vault (Obsidian-style notes) for usage cards."""
    repo_root = None
    if _context and _context.get("repo_root"):
        repo_root = Path(str(_context["repo_root"]))
    else:
        import os

        env = os.environ.get("MANGO_REPO_ROOT", "").strip()
        if env:
            repo_root = Path(env)

    # Prefer in-process vault (host on PYTHONPATH); fall back to reading curated/
    try:
        from mango_studio_host.api_vault import lookup_api

        return lookup_api(query, repo_root=repo_root, limit=int(limit))
    except ImportError:
        pass

    # Sidecar may not have host package — read curated markdown directly
    from pathlib import Path as P

    candidates = []
    if repo_root:
        candidates.append(P(repo_root) / "apps" / "roblox-studio" / "curated")
    here = P(__file__).resolve()
    for parent in here.parents:
        c = parent / "apps" / "roblox-studio" / "curated"
        if c.is_dir():
            candidates.append(c)
            break
    # Minimal inline search
    import re

    heading = re.compile(r"^##\s+(.+?)\s*$", re.M)
    q = query.strip().lower()
    terms = [t for t in re.split(r"[\s,;/|]+", q) if t]
    cards: list[dict[str, Any]] = []
    for root in candidates:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            matches = list(heading.finditer(text))
            for i, m in enumerate(matches):
                title = m.group(1).strip()
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                body = text[start:end].strip()
                blob = f"{title}\n{body}".lower()
                score = sum(5 if t in title.lower() else blob.count(t) for t in terms)
                if score:
                    cards.append({"title": title, "body": body[:2500], "score": score})
        break
    cards.sort(key=lambda c: -int(c["score"]))
    top = cards[: max(1, min(int(limit), 5))]
    if not top:
        return {"ok": False, "error": "no_match", "query": query}
    return {
        "ok": True,
        "query": query,
        "cards": [{"title": c["title"], "body": c["body"]} for c in top],
    }


def register_rbx_api(registry: Any) -> None:
    registry.register(
        "rbx_api",
        rbx_api,
        description="Look up Roblox/Luau API usage notes (vault). Call before inventing APIs.",
        parameters={
            "query": {
                "type": "string",
                "description": "API topic e.g. RemoteEvent, TweenService, Players, DataStore",
            },
            "limit": {"type": "integer", "description": "Max cards (default 3)", "default": 3},
        },
        required=["query"],
    )
