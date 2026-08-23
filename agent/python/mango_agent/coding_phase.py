"""Coding phase state machine — single source of truth for tool forcing.

The runner previously derived "what next" from a flag soup
(``_prefer_write_file`` / ``_prefer_insert_lines`` / ``_prefer_edit_gaps``)
that multiple code paths set in conflicting orders. The Discord-bot loop was
the result: syntax-broken files got ``insert_lines`` forced, skeletons were
counted as progress, and feedback told the model three different things.

This module collapses that into one explicit phase per turn:

RESEARCH       -> declare_apis / ask_epistemic (max 2 turns, plan gate owns it)
CODE_COMPLETE  -> no primary impl file yet        -> write_file only
CODE_REPAIR    -> syntax broken                   -> write_file only (never insert)
CODE_EXTEND    -> compiles, logic gaps open       -> insert_lines only
TEST           -> impl complete, tests required   -> run_tests
DONE           -> goal met                        -> no mutations

Golden rules encoded here:
1. Syntax beats everything: never insert/edit onto a file that does not compile.
2. Integration goals (bots/APIs) are not skeleton-mode: hollow writes get rejected.
3. One turn = one mutation = one closed work item; unchanged gaps escalate.
"""

from __future__ import annotations

from enum import Enum


class CodingPhase(Enum):
    RESEARCH = "research"
    CODE_COMPLETE = "code_complete"
    CODE_REPAIR = "code_repair"
    CODE_EXTEND = "code_extend"
    TEST = "test"
    DONE = "done"


# Tools the grammar may offer per phase. Everything else is stripped.
PHASE_TOOLS: dict[CodingPhase, tuple[str, ...]] = {
    CodingPhase.RESEARCH: ("declare_apis", "ask_epistemic", "research_codebase", "read_file", "search_code"),
    CodingPhase.CODE_COMPLETE: ("write_file",),
    CodingPhase.CODE_REPAIR: ("write_file",),
    CodingPhase.CODE_EXTEND: ("insert_lines", "write_file"),
    CodingPhase.TEST: ("run_tests", "write_file"),
    CodingPhase.DONE: (),
}

FORCED_TOOL: dict[CodingPhase, str | None] = {
    CodingPhase.RESEARCH: None,
    CodingPhase.CODE_COMPLETE: "write_file",
    CodingPhase.CODE_REPAIR: "write_file",
    CodingPhase.CODE_EXTEND: "insert_lines",
    CodingPhase.TEST: None,
    CodingPhase.DONE: None,
}

# Phases where attention must be 100% on code — trim prompt + thought.
CODING_PHASES = frozenset(
    {CodingPhase.CODE_COMPLETE, CodingPhase.CODE_REPAIR, CodingPhase.CODE_EXTEND}
)

THOUGHT_CAP_TOKENS = 64


def resolve_coding_phase(
    *,
    plan_gate_phase: str | None,
    syntax_broken: bool,
    collection_error: bool,
    primary_impl_exists: bool,
    has_logic_gaps: bool,
    task_wants_tests: bool,
    ran_tests_ok: bool,
    test_files_exist: bool,
    tests_uncollectable: bool,
) -> CodingPhase:
    """Priority-ordered resolution. Syntax always wins over gaps."""
    if tests_uncollectable:
        return CodingPhase.CODE_REPAIR
    if syntax_broken or collection_error:
        return CodingPhase.CODE_REPAIR
    if plan_gate_phase is not None:
        return CodingPhase.RESEARCH
    if not primary_impl_exists:
        return CodingPhase.CODE_COMPLETE
    if has_logic_gaps:
        return CodingPhase.CODE_EXTEND
    if task_wants_tests and (not ran_tests_ok or not test_files_exist):
        return CodingPhase.TEST
    return CodingPhase.DONE


def forced_tool_for_phase(phase: CodingPhase, enabled: set[str]) -> str | None:
    tool = FORCED_TOOL.get(phase)
    if tool is None:
        return None
    if tool in enabled:
        return tool
    # Fallbacks keep the loop moving when a tool is disabled.
    fallbacks = {CodingPhase.CODE_EXTEND: "write_file"}.get(phase)
    for candidate in (fallbacks,) if fallbacks else ():
        if candidate in enabled:
            return candidate
    return None
