"""Wire Rojo detection into /health and optional workspace hint on /v1/run."""

from __future__ import annotations

# Re-export for callers
from mango_studio_host.rojo import find_rojo_project, rojo_tree_root

__all__ = ["find_rojo_project", "rojo_tree_root"]
