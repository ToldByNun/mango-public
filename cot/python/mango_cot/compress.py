from __future__ import annotations

from mango_cot.types import ReasoningState

DEFAULT_SUMMARY_CHARS = 720


def compress_reasoning_state(
    reasoning_state: ReasoningState,
    *,
    max_chars: int = DEFAULT_SUMMARY_CHARS,
) -> str:
    """Compact summary for the action prompt — never the full reasoning state."""
    if reasoning_state.is_empty():
        return ""

    lines: list[str] = []
    if reasoning_state.next_action.strip():
        lines.append("Next: " + _clip(reasoning_state.next_action, 160))
    _extend_bullets(lines, "Facts", reasoning_state.known_facts, 3, 100)
    _extend_bullets(lines, "Decisions", reasoning_state.decisions, 2, 100)
    # Assumptions before Avoid: long verification dumps used to truncate the
    # Assume line under the action-prompt char budget, dropping the next fix.
    if reasoning_state.assumptions:
        _extend_bullets(lines, "Assume", reasoning_state.assumptions, 2, 120)
    _extend_bullets(lines, "Avoid", reasoning_state.failed_attempts, 2, 80)
    _extend_bullets(lines, "Open", reasoning_state.open_questions, 2, 100)

    summary = "\n".join(lines).strip()
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 16].rstrip() + "\n...[compressed]"


def thought_for_ui(reasoning_state: ReasoningState) -> str:
    """Plain-language thought for the GUI. Never dump Chain:/thoughtN metadata."""
    action = reasoning_state.next_action.strip()
    fact = reasoning_state.known_facts[-1].strip() if reasoning_state.known_facts else ""
    if action and fact and fact.lower() not in action.lower():
        return _clip(f"{action}. {fact}", 280)
    return _clip(action or fact, 280)


def _extend_bullets(
    lines: list[str],
    label: str,
    values: list[str],
    keep: int,
    item_limit: int,
) -> None:
    if not values:
        return
    clipped = [_clip(item, item_limit) for item in values[-keep:]]
    lines.append(f"{label}: " + " | ".join(clipped))


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
