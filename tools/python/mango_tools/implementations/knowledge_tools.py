"""Tiered knowledge tools: project_brief, rag_search, vault_open."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mango_tools import knowledge as kn


def _repo_from_context(_context: dict[str, Any] | None) -> Path | None:
    if _context and _context.get("repo_root"):
        return Path(str(_context["repo_root"]))
    import os

    env = os.environ.get("MANGO_REPO_ROOT", "").strip()
    return Path(env) if env else None


def project_brief(_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tier 1 — instant one-liner / short project pitch."""
    return kn.read_brief(_repo_from_context(_context))


def rag_search(
    query: str,
    *,
    limit: int = 5,
    refresh: bool = False,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tier 2 — medium RAG over indexed knowledge chunks (SQLite FTS5)."""
    return kn.rag_search(
        query,
        repo_root=_repo_from_context(_context),
        limit=int(limit),
        refresh=bool(refresh),
    )


def vault_open(
    name: str,
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tier 3 — open a markdown vault note (supports [[wikilinks]] targets)."""
    return kn.open_vault_note(name, repo_root=_repo_from_context(_context))


def knowledge_reindex(_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Rebuild the RAG index from BRIEF + vault + playbooks + curated."""
    return kn.refresh_index(_repo_from_context(_context))


def register_knowledge_tools(registry: Any, *, include_reindex: bool = False) -> None:
    registry.register(
        "project_brief",
        project_brief,
        description="Tier-1 instant project one-liner (knowledge/BRIEF.md). Use first for orientation.",
        parameters={},
        required=[],
    )
    registry.register(
        "rag_search",
        rag_search,
        description=(
            "Tier-2 medium RAG: search indexed knowledge chunks (vault, playbooks, curated). "
            "Use when you need fuzzy recall without reading whole notes."
        ),
        parameters={
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max hits (default 5)", "default": 5},
            "refresh": {
                "type": "boolean",
                "description": "Rebuild index before search",
                "default": False,
            },
        },
        required=["query"],
    )
    registry.register(
        "vault_open",
        vault_open,
        description=(
            "Tier-3 full markdown note from knowledge/vault (Obsidian-style [[wikilinks]]). "
            "Clearest explanations; follow returned links if needed."
        ),
        parameters={
            "name": {
                "type": "string",
                "description": "Note title, filename, or [[wikilink]] target",
            },
        },
        required=["name"],
    )
    if include_reindex:
        registry.register(
            "knowledge_reindex",
            knowledge_reindex,
            description="Rebuild the knowledge RAG index.",
            parameters={},
            required=[],
        )
