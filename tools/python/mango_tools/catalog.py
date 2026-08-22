"""Single source of truth for tool catalog sync (A2).

Keeps registry names, GBNF required-key map, parser aliases, and event titles aligned.
"""

from __future__ import annotations

from typing import Any

# Canonical tool names exposed to the model (subset may be gated by flags).
CATALOG: dict[str, dict[str, Any]] = {
    "read_file": {
        "required": ("path",),
        "aliases": ("read", "open_file"),
        "title": "Reading file",
    },
    "list_dir": {
        "required": (),
        "aliases": ("ls", "list_directory"),
        "title": "Listing directory",
    },
    "glob_files": {
        "required": ("pattern",),
        "aliases": ("glob", "find_files"),
        "title": "Finding files",
    },
    "write_file": {
        "required": ("path", "content"),
        "aliases": ("write", "create_file"),
        "title": "Writing file",
    },
    "edit_file": {
        "required": ("path", "old_string", "new_string"),
        "aliases": ("edit", "str_replace"),
        "title": "Editing file",
    },
    "delete_file": {
        "required": ("path",),
        "aliases": ("delete", "rm"),
        "title": "Deleting file",
    },
    "edit_symbol": {
        "required": ("path", "symbol", "body"),
        "aliases": (),
        "title": "Editing symbol",
    },
    "rename_symbol": {
        "required": ("old_name", "new_name"),
        "aliases": (),
        "title": "Renaming symbol",
    },
    "search_code": {
        "required": ("pattern",),
        "aliases": ("grep", "search"),
        "title": "Searching code",
    },
    "measure": {
        "required": ("command",),
        "aliases": (),
        "title": "Measuring",
    },
    "run_tests": {
        "required": (),
        "aliases": ("pytest", "test"),
        "title": "Running tests",
    },
    "run_terminal_command": {
        "required": ("command",),
        "aliases": ("shell", "bash"),
        "title": "Running command",
    },
    "declare_apis": {
        "required": ("libraries",),
        "aliases": (),
        "title": "Declaring APIs",
    },
    "ask_epistemic": {
        "required": ("question",),
        "aliases": (),
        "title": "Asking epistemic",
    },
    "research_codebase": {
        "required": ("question",),
        "aliases": ("research_topic", "codebase_research"),
        "title": "Researching codebase",
    },
    "codebase_lookup": {
        "required": ("query",),
        "aliases": (),
        "title": "Looking up codebase",
    },
}


def catalog_names() -> list[str]:
    return sorted(CATALOG)


def required_keys_map() -> dict[str, tuple[str, ...]]:
    return {name: tuple(meta.get("required") or ()) for name, meta in CATALOG.items()}


def alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name, meta in CATALOG.items():
        mapping[name] = name
        for alias in meta.get("aliases") or ():
            mapping[str(alias)] = name
    return mapping


def event_title(name: str, arguments: dict[str, Any] | None = None) -> str | None:
    meta = CATALOG.get(name)
    if meta is None:
        return None
    return str(meta.get("title") or name.replace("_", " "))
