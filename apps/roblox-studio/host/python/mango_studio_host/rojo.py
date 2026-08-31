"""Optional Rojo project detection for hybrid filesystem + DataModel mode."""

from __future__ import annotations

from pathlib import Path


def find_rojo_project(start: Path | None = None) -> Path | None:
    """Return default.project.json if found walking up from start (or cwd)."""
    cur = (start or Path.cwd()).resolve()
    for _ in range(8):
        candidate = cur / "default.project.json"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def rojo_tree_root(project_file: Path) -> Path | None:
    """Best-effort: directory containing default.project.json is the sync root."""
    if project_file.is_file():
        return project_file.parent
    return None
