from __future__ import annotations

from copy import deepcopy
from typing import Callable, Sequence

from mango_context.ast_slice import DEFAULT_BODY_LINES, focus_symbols_from_text, slice_source
from mango_context.types import ActionRecord, ContextState, ToolResultEntry

SourceSlicer = Callable[..., str]

_CODE_TOOLS = frozenset(
    {"read_file", "write_file", "edit_file", "edit_symbol", "rename_symbol", "search_code"}
)
_MAX_RENDERED_ACTIONS = 12
_SUMMARY_CHARS = 180


def focus_from_state(state: ContextState) -> tuple[str, ...]:
    extra = [str(name) for name in (state.verification_impl_symbols or []) if name]
    return focus_symbols_from_text(state.goal, *extra)


def apply_context_guard(
    state: ContextState,
    *,
    slicer: SourceSlicer | None = None,
) -> tuple[list[ActionRecord], list[ToolResultEntry]]:
    """Compress history for the next model call: AST slices + old-result summaries."""
    actions = list(state.previous_actions[-_MAX_RENDERED_ACTIONS:])
    results = deepcopy(state.tool_results)
    keep_recent = max(1, state.budget.keep_recent_results)
    focus = focus_from_state(state)
    body_lines = getattr(state.budget, "body_lines", DEFAULT_BODY_LINES)
    impl = slicer or slice_source

    for index, entry in enumerate(results):
        is_recent = index >= max(0, len(results) - keep_recent)
        if is_recent:
            entry.body = _slice_result_body(entry, impl, focus=focus, body_lines=body_lines)
        else:
            entry.body = _summarize_result(entry)
    return actions, results


def ingest_result_into_memory(
    state: ContextState,
    *,
    tool_name: str,
    body: str,
    paths: Sequence[str],
    iteration: int,
    slicer: SourceSlicer | None = None,
) -> None:
    """Update deterministic memory after a tool result is recorded."""
    del slicer
    memory = state.memory
    if tool_name == "read_file":
        path, content = _split_path_content(body)
        target = path or (paths[0] if paths else "")
        if target:
            memory.upsert("file", target, content or body, iteration)
        return
    if tool_name in {"write_file", "edit_file", "edit_symbol", "rename_symbol"}:
        path = (paths[0] if paths else "") or _path_from_body(body)
        memory.upsert("write", path or "file", _one_line(body, 140), iteration)
        return
    if tool_name == "verification":
        memory.upsert("verify", "last", _one_line(body, 180), iteration)
        return
    if tool_name == "codebase_lookup":
        memory.upsert("lookup", str(iteration), _one_line(body, 140), iteration)


def remember_file_slice(
    state: ContextState,
    path: str,
    source: str,
    *,
    iteration: int,
    slicer: SourceSlicer | None = None,
) -> None:
    impl = slicer or slice_source
    focus = focus_from_state(state)
    body_lines = getattr(state.budget, "body_lines", DEFAULT_BODY_LINES)
    sliced = impl(source, path=path, focus_symbols=focus, body_lines=body_lines)
    state.memory.upsert("file", path, sliced, iteration)


def _slice_result_body(
    entry: ToolResultEntry,
    slicer: SourceSlicer,
    *,
    focus: Sequence[str],
    body_lines: int,
) -> str:
    if entry.tool_name != "read_file":
        return _cap_body(entry.body, 1_200)
    path, content = _split_path_content(entry.body)
    if not content.strip():
        return _cap_body(entry.body, 1_200)
    sliced = slicer(content, path=path, focus_symbols=focus, body_lines=body_lines)
    prefix = f"path: {path}\n" if path else ""
    return prefix + sliced


def _summarize_result(entry: ToolResultEntry) -> str:
    path, _content = _split_path_content(entry.body)
    if entry.tool_name == "read_file":
        where = path or "file"
        return f"[compact] read {where} ({entry.original_chars} chars) → see Memory"
    if entry.tool_name in {"write_file", "edit_file", "edit_symbol"}:
        return f"[compact] {entry.tool_name} {_one_line(entry.body, 100)}"
    if entry.tool_name == "verification":
        return f"[compact] {_one_line(entry.body, 140)}"
    if entry.tool_name in _CODE_TOOLS:
        return f"[compact] {entry.tool_name}: {_one_line(entry.body, 100)}"
    return f"[compact] {entry.tool_name}: {_one_line(entry.body, _SUMMARY_CHARS)}"


def _split_path_content(body: str) -> tuple[str, str]:
    text = body or ""
    if text.startswith("path: "):
        first, _, rest = text.partition("\n")
        return first[6:].strip(), rest
    return "", text


def _path_from_body(body: str) -> str:
    text = body or ""
    if '"path"' in text:
        start = text.find('"path"')
        chunk = text[start : start + 180]
        if ":" in chunk:
            value = chunk.split(":", 1)[1].strip().strip(",").strip('"')
            return value
    if text.startswith("path: "):
        return text.split("\n", 1)[0][6:].strip()
    return ""


def _cap_body(body: str, limit: int) -> str:
    if len(body) <= limit:
        return body
    return body[: limit - 16].rstrip() + "\n...[compacted]"


def _one_line(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
