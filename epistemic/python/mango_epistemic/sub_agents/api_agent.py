from __future__ import annotations

from typing import Any, Callable

from mango_epistemic.research_tools import doc_lookup, package_source_lookup, web_research
from mango_tools.tool_registry import ToolRegistry

WebBackend = Callable[[str], Any]


def create_api_research_registry(
    *,
    web_backend: WebBackend | None = None,
) -> ToolRegistry:
    """Tools for the isolated API sub-agent. Does not include ask_epistemic."""
    registry = ToolRegistry()
    context = {"web_research_backend": web_backend} if web_backend else {}

    def _web_research(query: str, max_results: int = 5, _context: dict | None = None) -> dict:
        merged = dict(context)
        if _context:
            merged.update(_context)
        return web_research(query, max_results=max_results, _context=merged)

    registry.register(
        "web_research",
        _web_research,
        description="Search the web for API/docs evidence when import/inspect is not enough.",
        parameters={
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5},
        },
        required=["query"],
    )
    registry.register(
        "doc_lookup",
        doc_lookup,
        description="Inspect a library/symbol and return its source (or C-extension docstring) as a usage card.",
        parameters={
            "library": {"type": "string"},
            "symbol": {"type": "string", "default": ""},
        },
        required=["library"],
    )
    registry.register(
        "package_source_lookup",
        package_source_lookup,
        description="Inspect an installed package/symbol and return its source (or C-extension docstring) as a usage card.",
        parameters={
            "package": {"type": "string"},
            "symbol": {"type": "string", "default": ""},
        },
        required=["package"],
    )
    return registry
