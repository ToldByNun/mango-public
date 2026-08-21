from __future__ import annotations

from pathlib import Path
from typing import Any

_STRIP_ROOT_PARTS = frozenset({"home", "workspace", "project", "repo", "src"})


def normalize_tool_path(path: str) -> str:
    """Strip model-invented prefixes (e.g. home/user/math_utils.py -> math_utils.py)."""
    raw = path.strip().replace("\\", "/").lstrip("/")
    parts = [p for p in raw.split("/") if p and p not in {".", ".."}]
    if not parts:
        return raw
    lowered = [p.lower() for p in parts]
    if "user" in lowered:
        idx = lowered.index("user")
        parts = parts[idx + 1 :]
    while parts and parts[0].lower() in _STRIP_ROOT_PARTS:
        parts = parts[1:]
    if not parts:
        return Path(raw).name
    return "/".join(parts)


def resolve_tool_path(path: str, context: dict[str, Any] | None = None) -> Path:
    """Resolve a tool path against the workspace when the model passed a relative path.

    Prefer a path that actually exists, including real `src/` layouts. Fall back to
    stripping invented prefixes such as `src/math_utils.py` when that file is at the
    workspace root.
    """
    original = path.strip().replace("\\", "/")
    orig_path = Path(original).expanduser()
    if orig_path.is_absolute() and orig_path.exists():
        return orig_path.resolve()

    normalized = normalize_tool_path(path)
    workspace = (context or {}).get("workspace")
    if not workspace:
        raw = Path(normalized or original).expanduser()
        return raw.resolve()

    ws = Path(str(workspace))
    candidates: list[Path] = []
    if orig_path.is_absolute():
        candidates.append(orig_path)
    else:
        rel = original.lstrip("/")
        if rel:
            candidates.append(ws / rel)
    if normalized:
        candidates.append(ws / normalized)
        if not normalized.lower().startswith("src/"):
            candidates.append(ws / "src" / normalized)

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate.resolve()
    return (ws / (normalized or original.lstrip("/"))).resolve()


def display_tool_path(file_path: Path, context: dict[str, Any] | None = None) -> str:
    workspace = (context or {}).get("workspace")
    if workspace:
        try:
            rel = file_path.resolve().relative_to(Path(str(workspace)).resolve())
            return str(rel).replace("\\", "/")
        except ValueError:
            pass
    return file_path.name


def file_tool_result(file_path: Path, context: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    result = {
        "path": display_tool_path(file_path, context),
        "absolute_path": str(file_path.resolve()),
        **extra,
    }
    return result
