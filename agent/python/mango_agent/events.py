from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

STARTED = "agent.started"
THOUGHT = "agent.thought"
TOKEN = "agent.token"
TOOL = "agent.tool"
FILE = "agent.file"
VERIFICATION = "agent.verification"
SYNTAX = "agent.syntax"
EXPERIMENT = "agent.experiment"
CHECKPOINT = "agent.checkpoint"
METRICS = "agent.metrics"
PHASE = "agent.phase"
FINAL = "agent.final"
STOPPED = "agent.stopped"
ERROR = "agent.error"


def line_stats(old: str, new: str) -> tuple[int, int]:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    added = 0
    removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1
    return added, removed


def unified_diff(path: str, old: str, new: str, *, limit: int = 8_000) -> str:
    name = Path(path).name
    lines = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"a/{name}",
        tofile=f"b/{name}",
        lineterm="",
    )
    text = "\n".join(lines)
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def tool_title(name: str, arguments: dict[str, Any] | None = None) -> str:
    args = arguments or {}
    if name == "run_tests":
        return "Ran tests"
    if name == "measure":
        command = str(args.get("command") or "").strip()
        return f"Measured {command}" if command else "Measured"
    if name == "search_code":
        query = str(args.get("query") or args.get("pattern") or args.get("text") or "").strip()
        path = str(args.get("path") or args.get("glob") or args.get("include") or "").strip()
        if query and path:
            return f"Searching `{query}` in {path}"
        if query:
            return f"Searching `{query}`"
        if path:
            return f"Searching files `{path}`"
        return "Searching"
    if name == "read_file":
        path = str(args.get("path") or "").strip()
        return f"Reading `{Path(path).name}`" if path else "Reading file"
    if name == "list_dir":
        path = str(args.get("path") or ".").strip()
        return f"Listing `{path}`"
    if name == "glob_files":
        pattern = str(args.get("pattern") or "").strip()
        return f"Finding `{pattern}`" if pattern else "Finding files"
    if name == "delete_file":
        path = str(args.get("path") or "").strip()
        return f"Deleting `{Path(path).name}`" if path else "Deleting file"
    if name == "codebase_lookup":
        symbol = args.get("symbol") or args.get("query") or args.get("name")
        return f"Looked up symbol {symbol}" if symbol else "Looked up symbol"
    if name == "run_terminal_command":
        command = str(args.get("command") or args.get("cmd") or "").strip()
        return f"Ran {command}" if command else "Ran command"
    if name == "ask_epistemic":
        return "Asked epistemic sub-agent"
    if name == "declare_apis":
        libs = args.get("libraries") or args.get("apis") or ""
        return f"Declared APIs {libs}" if libs else "Declared APIs"
    if name in {"package_source_lookup", "doc_lookup"}:
        package = str(args.get("package") or args.get("library") or "").strip()
        symbol = str(args.get("symbol") or "").strip()
        target = f"{package}.{symbol}" if package and symbol else package or symbol
        return f"Inspected {target}" if target else "Inspected library"
    if name == "web_research":
        query = str(args.get("query") or "").strip()
        return f"Searched {query}" if query else "Searched the web"
    return name.replace("_", " ")


def read_range(content: str) -> tuple[int, int]:
    if not content:
        return 1, 1
    lines = content.count("\n") + (0 if content.endswith("\n") else 1)
    return 1, max(1, lines)
