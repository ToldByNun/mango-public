from __future__ import annotations

from mango_context.guard import apply_context_guard
from mango_context.types import ActionRecord, ContextState, ToolResultEntry

STUB_MIN_CHARS = 96
TRUNC_SUFFIX = "\n...[truncated]"


def build_prompt(context_state: ContextState) -> str:
    """Assemble a compact prompt from ContextState, fitting the configured budget.

    A context guard first replaces raw code with AST slices and old tool
    outputs with summaries. Remaining overflow is truncated oldest-first.
    The goal is never shortened.
    """
    actions, results = apply_context_guard(context_state)
    limit = context_state.budget.char_limit

    prompt = _render(context_state, actions, results)
    if len(prompt) <= limit:
        return prompt

    _shrink_old_result_bodies(results, context_state, actions, limit)
    prompt = _render(context_state, actions, results)
    if len(prompt) <= limit:
        return prompt

    _omit_old_result_bodies(results, context_state, actions, limit)
    prompt = _render(context_state, actions, results)
    if len(prompt) <= limit:
        return prompt

    while len(actions) > 3 and len(_render(context_state, actions, results)) > limit:
        actions.pop(0)

    while len(results) > max(1, context_state.budget.keep_recent_results):
        prompt = _render(context_state, actions, results)
        if len(prompt) <= limit:
            return prompt
        results.pop(0)

    for entry in results:
        if len(_render(context_state, actions, results)) <= limit:
            break
        entry.body = _truncate_body(entry.body, STUB_MIN_CHARS)

    return _render(context_state, actions, results)


def _truncate_body(body: str, target_len: int) -> str:
    if len(body) <= target_len:
        return body
    cut = max(0, target_len - len(TRUNC_SUFFIX))
    return body[:cut].rstrip() + TRUNC_SUFFIX


def _shrink_old_result_bodies(
    results: list[ToolResultEntry],
    state: ContextState,
    actions: list[ActionRecord],
    limit: int,
) -> None:
    keep_recent = state.budget.keep_recent_results
    shrinkable = results[:-keep_recent] if keep_recent else results
    for entry in shrinkable:
        if len(_render(state, actions, results)) <= limit:
            return
        entry.body = _truncate_body(entry.body, STUB_MIN_CHARS)


def _omit_old_result_bodies(
    results: list[ToolResultEntry],
    state: ContextState,
    actions: list[ActionRecord],
    limit: int,
) -> None:
    keep_recent = state.budget.keep_recent_results
    omit_upto = max(0, len(results) - keep_recent)
    for entry in results[:omit_upto]:
        if len(_render(state, actions, results)) <= limit:
            return
        entry.body = f"(omitted {entry.original_chars} chars)"


def _render(
    state: ContextState,
    actions: list[ActionRecord],
    results: list[ToolResultEntry],
) -> str:
    sections: list[str] = []

    if state.system_prompt.strip():
        sections.append(state.system_prompt.strip())
    if state.tool_instruction.strip():
        sections.append(state.tool_instruction.strip())
    if state.available_tools:
        lines = [f"- {tool.name}: {tool.description}" for tool in state.available_tools]
        sections.append("Available tools:\n" + "\n".join(lines))

    sections.append(f"## Goal\n{state.goal.strip()}")

    memory_text = ""
    if getattr(state, "memory", None) is not None and not state.memory.is_empty():
        memory_text = state.memory.render(max_chars=state.budget.memory_max_chars)
    if memory_text:
        sections.append("## Memory\n" + memory_text)

    if state.reasoning_summary.strip():
        sections.append(
            "## Compressed reasoning summary\n" + state.reasoning_summary.strip()
        )

    if state.constraints:
        bullets = "\n".join(f"- {item}" for item in state.constraints)
        sections.append(f"## Constraints\n{bullets}")

    if state.relevant_files:
        files = "\n".join(f"- {path}" for path in state.relevant_files)
        sections.append(f"## Relevant files\n{files}")

    if actions:
        lines = [f"- [{item.iteration}] {item.summary}" for item in actions]
        sections.append("## Previous actions\n" + "\n".join(lines))

    if results:
        blocks = [_format_result(entry) for entry in results]
        sections.append("## Tool results\n" + "\n\n".join(blocks))

    # Volatile runner feedback last so KV prefix (system + goal + tool history) stays stable.
    if state.verification_feedback.strip():
        sections.append("## Verification\n" + state.verification_feedback.strip())

    next_bit = (
        "Continue the goal. Emit one tool call, or give the final answer if the task is done."
    )
    status = _verification_next_status(state)
    if status == "collection":
        next_bit = _collection_next_bit(state, idle=False)
    elif state.allow_multi_edit and status == "failed":
        next_bit = _failed_next_bit(
            state,
            idle=False,
            extra=(
                "Verification failed across multiple implementation files. "
                "You MAY emit multiple edit_symbol/write_file/rename_symbol tool calls in this turn "
                "(one per affected file), then stop. Do not give a final answer yet."
            ),
        )
    elif status == "failed":
        next_bit = _failed_next_bit(state, idle=False)
    elif status == "passed":
        next_bit = "Verification passed. Reply with a short summary and NO tool calls."
    sections.append("## Next\n" + next_bit)
    return "\n\n".join(sections) + "\n"


def build_idle_retry_prompt(context_state: ContextState) -> str:
    """Tiny follow-up after a no-tool reply so idle turns do not resend the full window."""
    sections: list[str] = [
        "Your previous reply had no tool call. Do not give a final answer.",
    ]
    if context_state.tool_instruction.strip():
        sections.append(context_state.tool_instruction.strip())
    sections.append(f"## Goal\n{context_state.goal.strip()}")
    if getattr(context_state, "memory", None) is not None and not context_state.memory.is_empty():
        memory_text = context_state.memory.render(max_chars=min(800, context_state.budget.memory_max_chars))
        if memory_text:
            sections.append("## Memory\n" + memory_text)
    if context_state.verification_feedback.strip():
        sections.append("## Verification\n" + context_state.verification_feedback.strip())
    if context_state.relevant_files:
        files = "\n".join(f"- {path}" for path in context_state.relevant_files[-8:])
        sections.append(f"## Relevant files\n{files}")
    status = _verification_next_status(context_state)
    if status == "collection":
        next_bit = _collection_next_bit(context_state, idle=True)
    elif status == "failed":
        next_bit = _failed_next_bit(context_state, idle=True)
    else:
        next_bit = (
            "Emit a tool call now (edit_symbol, read_file, or write_file). "
            "Do not finish yet."
        )
    sections.append("## Next\n" + next_bit)
    return "\n\n".join(sections) + "\n"


def _collection_next_bit(state: ContextState, *, idle: bool) -> str:
    parts: list[str] = []
    current = str(getattr(state, "verification_current_source", "") or "").strip()
    if current:
        parts.append(f"Broken file currently:\n{current}")
    missing = getattr(state, "verification_missing_symbol", None)
    module = getattr(state, "verification_missing_module", None)
    if missing:
        loc = f"{module}.py" if module else "the implementation module"
        parts.append(f"Define missing symbol {missing} in {loc}; do not change the test.")
    else:
        parts.append(
            "Tests could not be collected because a module is broken (syntax/import). "
            "Repair it with write_file or edit_file."
        )
    parts.append("Do not finish yet." if idle else "Do not give a final answer.")
    return "\n".join(parts)


def _failed_next_bit(state: ContextState, *, idle: bool, extra: str = "") -> str:
    parts: list[str] = []
    noop = str(getattr(state, "last_noop_snippet", "") or "").strip()
    current = str(getattr(state, "verification_current_source", "") or "").strip()
    hint = str(getattr(state, "verification_next_edit", "") or "").strip()
    if noop:
        parts.append(f"Last write did not change the file. Current body still:\n{noop}")
    elif current:
        parts.append(f"Current implementation:\n{current}")
    if hint:
        parts.append(hint)
    feedback = str(getattr(state, "verification_feedback", "") or "")
    if "TypeError" in feedback or "AttributeError" in feedback:
        parts.append(
            "If a TypeError or AttributeError occurs, inspect the input types "
            "(isinstance or a short print) before calling methods on them."
        )
    if extra:
        parts.append(extra)
    elif idle:
        parts.append("Verification failed. Emit edit_symbol or write_file with a different body. Do not finish yet.")
    else:
        parts.append(
            "Verification failed. Change the implementation body; do not rewrite the same text. "
            "Do not give a final answer until verification passes."
        )
    return "\n".join(parts)


def _verification_next_status(state: ContextState) -> str:
    if getattr(state, "verification_collection_error", False):
        return "collection"
    feedback = str(state.verification_feedback or "").lower()
    if "collection error" in feedback:
        return "collection"
    if "verification failed" in feedback:
        return "failed"
    if str(getattr(state, "last_noop_snippet", "") or "").strip():
        return "failed"
    if "verification passed" in feedback:
        return "passed"
    return ""


def _format_result(entry: ToolResultEntry) -> str:
    status = "ok" if entry.success else "error"
    header = f"### [{entry.iteration}] {entry.tool_name} ({status})"
    parts = [header]
    if entry.error:
        parts.append(f"error: {entry.error}")
    if entry.body:
        parts.append(entry.body)
    return "\n".join(parts)
