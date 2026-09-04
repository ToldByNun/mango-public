"""lookup_playbook — retrieve procedural \"when X, do Y\" runbooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mango_tools.playbooks import lookup_playbook as _lookup


def lookup_playbook(
    query: str,
    *,
    limit: int = 2,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find a playbook for a multi-step workflow (login, setup, deploy, …)."""
    repo_root = None
    if _context and _context.get("repo_root"):
        repo_root = Path(str(_context["repo_root"]))
    else:
        import os

        env = os.environ.get("MANGO_REPO_ROOT", "").strip()
        if env:
            repo_root = Path(env)
    return _lookup(query, repo_root=repo_root, limit=int(limit))


def register_lookup_playbook(registry: Any) -> None:
    registry.register(
        "lookup_playbook",
        lookup_playbook,
        description=(
            "Look up a procedural playbook (when X happens → ordered steps). "
            "Use for login, browser flows, deploy, Studio host setup — before inventing steps."
        ),
        parameters={
            "query": {
                "type": "string",
                "description": "Workflow keywords e.g. 'playwright login xyz', 'roblox host start'",
            },
            "limit": {"type": "integer", "description": "Max playbooks (default 2)", "default": 2},
        },
        required=["query"],
    )
