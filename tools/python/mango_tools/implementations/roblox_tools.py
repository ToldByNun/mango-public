"""Remote Roblox Studio tools — executed by the Studio plugin via host bridge."""

from __future__ import annotations

from typing import Any

from mango_tools.studio_dispatch import dispatch_studio_tool

# Hard caps for small local models (tokens + robustness).
_EDIT_MAX_CHARS = 4000
_CREATE_SEED_MAX_CHARS = 1500
_DEFAULT_PROP_CONFIRM_THRESHOLD = 1


def _ctx_threshold(_context: dict[str, Any] | None) -> int:
    if not _context:
        return _DEFAULT_PROP_CONFIRM_THRESHOLD
    raw = _context.get("confirm_prop_threshold")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_PROP_CONFIRM_THRESHOLD


def rbx_tree(
    path: str = "game",
    *,
    depth: int = 3,
    max_nodes: int = 200,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """List Instance hierarchy under path."""
    return dispatch_studio_tool(
        "rbx_tree",
        {"path": path, "depth": int(depth), "max_nodes": int(max_nodes)},
    )


def rbx_sel(
    *,
    paths: list[str] | None = None,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get current selection, or set selection when paths is provided."""
    args: dict[str, Any] = {}
    if paths is not None:
        args["paths"] = list(paths)
    return dispatch_studio_tool("rbx_sel", args)


def rbx_read(
    path: str,
    *,
    what: str = "source",
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read script source (what=source) or key properties (what=props)."""
    return dispatch_studio_tool("rbx_read", {"path": path, "what": what})


def rbx_edit(
    path: str,
    old: str,
    new: str,
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search/replace unique snippet in a Script/ModuleScript/LocalScript source.

    No full overwrite — old must match exactly once.
    """
    if len(old) > _EDIT_MAX_CHARS or len(new) > _EDIT_MAX_CHARS:
        return {
            "ok": False,
            "error": "edit_too_large",
            "detail": f"old/new capped at {_EDIT_MAX_CHARS} chars; split into smaller edits",
        }
    return dispatch_studio_tool("rbx_edit", {"path": path, "old": old, "new": new})


def rbx_create(
    parent: str,
    class_name: str,
    *,
    name: str = "",
    source: str = "",
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an Instance. Optional source seed only for new scripts (capped)."""
    if source and len(source) > _CREATE_SEED_MAX_CHARS:
        return {
            "ok": False,
            "error": "seed_too_large",
            "detail": (
                f"source seed capped at {_CREATE_SEED_MAX_CHARS} chars; "
                "create a stub then use rbx_edit"
            ),
        }
    return dispatch_studio_tool(
        "rbx_create",
        {
            "parent": parent,
            "className": class_name,
            "name": name,
            "source": source,
        },
    )


def rbx_prop(
    path: str = "",
    property_name: str = "",
    value: Any = None,
    *,
    paths: list[str] | None = None,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Set a property on one or more Instances. Bulk (>N) requires Studio confirm."""
    targets = list(paths) if paths else ([path] if path else [])
    if not targets or not property_name:
        return {"ok": False, "error": "missing_args", "detail": "path(s) and property_name required"}
    threshold = _ctx_threshold(_context)
    requires_confirm = len(targets) > threshold
    summary = f"Set {property_name} on {len(targets)} instance(s)"
    return dispatch_studio_tool(
        "rbx_prop",
        {
            "paths": targets,
            "propertyName": property_name,
            "value": value,
        },
        requires_confirm=requires_confirm,
        confirm_summary=summary if requires_confirm else "",
    )


def rbx_delete(
    path: str,
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delete an Instance. Always requires explicit Studio UI confirm before mutate."""
    return dispatch_studio_tool(
        "rbx_delete",
        {"path": path},
        requires_confirm=True,
        confirm_summary=f"Delete Instance {path}",
    )


def register_roblox_tools(registry: Any) -> None:
    """Register rbx_* tools on a ToolRegistry."""
    registry.register(
        "rbx_tree",
        rbx_tree,
        description="List Roblox Instance children under a path (Studio).",
        parameters={
            "path": {"type": "string", "description": "Instance path e.g. game.Workspace", "default": "game"},
            "depth": {"type": "integer", "description": "Max depth", "default": 3},
            "max_nodes": {"type": "integer", "description": "Cap nodes returned", "default": 200},
        },
        required=[],
    )
    registry.register(
        "rbx_sel",
        rbx_sel,
        description="Get or set Studio selection (paths list).",
        parameters={
            "paths": {
                "type": "array",
                "description": "If set, select these instance paths",
                "items": {"type": "string"},
            },
        },
        required=[],
    )
    registry.register(
        "rbx_read",
        rbx_read,
        description="Read script Source or properties from a Studio Instance.",
        parameters={
            "path": {"type": "string", "description": "Instance path"},
            "what": {"type": "string", "description": "source|props", "default": "source"},
        },
        required=["path"],
    )
    registry.register(
        "rbx_edit",
        rbx_edit,
        description="Search/replace a unique snippet in a Script source (no full overwrite).",
        parameters={
            "path": {"type": "string", "description": "Script instance path"},
            "old": {"type": "string", "description": "Exact unique substring to replace"},
            "new": {"type": "string", "description": "Replacement text"},
        },
        required=["path", "old", "new"],
    )
    registry.register(
        "rbx_create",
        rbx_create,
        description="Create an Instance; optional short source seed for new scripts only.",
        parameters={
            "parent": {"type": "string", "description": "Parent instance path"},
            "class_name": {"type": "string", "description": "ClassName e.g. Script, Part"},
            "name": {"type": "string", "description": "Instance Name", "default": ""},
            "source": {"type": "string", "description": "Optional seed source (capped)", "default": ""},
        },
        required=["parent", "class_name"],
    )
    registry.register(
        "rbx_prop",
        rbx_prop,
        description="Set a property on one or more Instances (bulk needs user confirm).",
        parameters={
            "path": {"type": "string", "description": "Single instance path", "default": ""},
            "paths": {
                "type": "array",
                "description": "Multiple instance paths for bulk set",
                "items": {"type": "string"},
            },
            "property_name": {"type": "string", "description": "Property name"},
            "value": {"description": "JSON-compatible value (Vector3 as {X,Y,Z})"},
        },
        required=["property_name"],
    )
    registry.register(
        "rbx_delete",
        rbx_delete,
        description="Delete an Instance (always requires user confirm in Studio).",
        parameters={
            "path": {"type": "string", "description": "Instance path to delete"},
        },
        required=["path"],
    )
