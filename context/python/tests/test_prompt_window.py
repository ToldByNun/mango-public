from __future__ import annotations

from mango_context import ContextBudget, ContextEngine, ContextState, ToolSpec, build_idle_retry_prompt, build_prompt, estimate_tokens


def test_build_prompt_includes_goal_and_structured_sections() -> None:
    state = ContextState(
        goal="Replace Mango with Agent in greeting.txt",
        constraints=["Do not create new files"],
        relevant_files=["greeting.txt"],
        system_prompt="You are Mango.",
        available_tools=[ToolSpec("read_file", "Read a file")],
        budget=ContextBudget(max_chars=8_000),
    )
    state.record_action(1, "read_file (ok)")
    state.record_tool_result(1, "read_file", True, "path: greeting.txt\nHello Mango\n")

    prompt = build_prompt(state)
    assert "## Goal" in prompt
    assert "Replace Mango with Agent in greeting.txt" in prompt
    assert "## Constraints" in prompt
    assert "## Relevant files" in prompt
    assert "## Previous actions" in prompt
    assert "## Tool results" in prompt
    assert "Hello Mango" in prompt
    assert prompt.count("Hello Mango") == 1


def test_build_prompt_includes_compact_verification_feedback() -> None:
    state = ContextState(
        goal="Implement function Y",
        verification_feedback="Verification failed (attempt 1/5)\nTests: 0 passed, 1 failed\n- test_y.py::test_Y",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "## Verification" in prompt
    assert "test_y.py::test_Y" in prompt
    assert "Do not give a final answer until verification passes" in prompt


def test_build_prompt_passed_feedback_does_not_look_like_failure() -> None:
    state = ContextState(
        goal="Implement function Y",
        verification_feedback="Verification passed (attempt 1/5)\nTests: 1 passed, 0 failed",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "Verification passed. Reply with a short summary and NO tool calls." in prompt
    assert "Do not give a final answer until verification passes" not in prompt


def test_idle_retry_prompt_is_compact_and_demands_a_tool_call() -> None:
    state = ContextState(
        goal="Implement function Y",
        tool_instruction="<tool_call=write_file : {\"path\": \"y.py\"}>",
        verification_feedback="Verification failed (attempt 1/5)\nTests: 0 passed, 1 failed",
        relevant_files=["y.py"],
        system_prompt="You are Mango. " * 40,
        available_tools=[ToolSpec("write_file", "Write a file")],
        budget=ContextBudget(max_chars=8_000),
    )
    state.record_action(1, "write_file (ok)")
    state.record_tool_result(1, "write_file", True, "wrote y.py\n" + ("x" * 800))
    compact = build_idle_retry_prompt(state)
    full = build_prompt(state)
    assert "## Goal" in compact
    assert "## Verification" in compact
    assert "Do not finish yet" in compact
    assert "Your previous reply had no tool call" in compact
    assert "You are Mango." not in compact
    assert "### [1] write_file" not in compact
    assert len(compact) < len(full)
    assert len(compact) < 1_200


def test_build_prompt_collection_error_asks_to_repair_module() -> None:
    state = ContextState(
        goal="Fix unique()",
        verification_feedback=(
            "Verification failed (attempt 1/5)\n"
            "COLLECTION ERROR: tests could not be imported. "
            "Repair syntax/imports in uniqueutil.py before changing assertions."
        ),
        verification_collection_error=True,
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "could not be collected" in prompt
    assert "Do not give a final answer" in prompt


def test_build_prompt_collection_error_asks_to_define_missing_symbol() -> None:
    state = ContextState(
        goal="Extract normalize",
        verification_feedback="Verification failed\nCOLLECTION ERROR",
        verification_collection_error=True,
        verification_missing_symbol="normalize",
        verification_missing_module="names",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "Define missing symbol normalize in names.py" in prompt
    assert "do not change the test" in prompt.lower()


def test_build_prompt_failed_includes_next_edit_hint() -> None:
    state = ContextState(
        goal="Implement money",
        verification_feedback="Verification failed (attempt 1/5)\nTests: 1 passed, 1 failed",
        verification_next_edit="Edit app/format.py symbol money: assert '90' == '$90.00'",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "Edit app/format.py symbol money" in prompt
    assert "Do not give a final answer until verification passes" in prompt


def test_build_prompt_failed_includes_current_implementation() -> None:
    state = ContextState(
        goal="Fix Y",
        verification_feedback="Verification failed (attempt 1/5)\nTests: 0 passed, 1 failed",
        verification_next_edit="Edit y.py symbol Y: assert 0 == 2",
        verification_current_source="y.py currently:\ndef Y(x):\n    return x - 1",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "Current implementation:" in prompt
    assert "return x - 1" in prompt
    assert "assert 0 == 2" in prompt


def test_build_prompt_noop_includes_unchanged_body() -> None:
    state = ContextState(
        goal="Fix Y",
        last_noop_snippet="y.py currently:\ndef Y(x):\n    return 0",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "Last write did not change the file" in prompt
    assert "return 0" in prompt


def test_build_prompt_type_error_asks_to_inspect_types() -> None:
    state = ContextState(
        goal="Fix parse_query",
        verification_feedback=(
            "Verification failed (attempt 1/5)\n"
            "Tests: 0 passed, 1 failed\n"
            "AttributeError: 'list' object has no attribute 'split'"
        ),
        verification_current_source="queryutil.py currently:\ndef parse_query(text):\n    return {}",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "AttributeError" in prompt
    assert "isinstance" in prompt
    assert "before calling methods" in prompt


def test_build_prompt_includes_compressed_reasoning_not_raw_dump() -> None:
    state = ContextState(
        goal="Fix import",
        reasoning_summary="Next: read util.py\nFacts: tests fail on import",
        budget=ContextBudget(max_chars=4_000),
    )
    prompt = build_prompt(state)
    assert "## Compressed reasoning summary" in prompt
    assert "Next: read util.py" in prompt
    assert "known_facts" not in prompt


def test_prompt_stays_under_char_budget_with_many_tool_results() -> None:
    limit = 4_000
    state = ContextState(
        goal="Fix the bug in main.py — this goal must survive truncation",
        system_prompt="You are a coding agent.",
        budget=ContextBudget(max_chars=limit, max_tokens=None),
    )
    blob = "X" * 1_200
    for i in range(1, 31):
        state.record_action(i, f"read_file file_{i}.txt (ok)")
        state.record_tool_result(
            i,
            "read_file",
            True,
            f"path: file_{i}.txt\n{blob}",
        )

    prompt = build_prompt(state)
    assert len(prompt) <= limit
    assert estimate_tokens(prompt) <= (limit + 3) // 4 + 1
    assert "Fix the bug in main.py — this goal must survive truncation" in prompt
    assert "[compact]" in prompt or "(omitted" in prompt or "...[truncated]" in prompt
    assert "X" * 400 not in prompt
    assert f"### [30] read_file" in prompt


def test_token_budget_caps_prompt() -> None:
    state = ContextState(
        goal="Keep this goal",
        budget=ContextBudget(max_chars=100_000, max_tokens=200),
    )
    for i in range(1, 20):
        state.record_tool_result(i, "read_file", True, "Y" * 2_000)

    prompt = build_prompt(state)
    assert len(prompt) <= 200 * 4
    assert "Keep this goal" in prompt


def test_context_engine_records_tool_results_and_files() -> None:
    engine = ContextEngine(
        "Edit notes.txt",
        tools=[("edit_file", "Replace text")],
        budget=ContextBudget(max_chars=6_000),
    )
    engine.record_turn(
        1,
        model_output="reading",
        tool_results=[
            {
                "success": True,
                "tool_name": "read_file",
                "output": {"path": "notes.txt", "content": "alpha"},
            }
        ],
    )
    prompt = engine.build_prompt()
    assert "Edit notes.txt" in prompt
    assert "notes.txt" in prompt
    assert "alpha" in prompt
    assert engine.state.relevant_files[-1].endswith("notes.txt")
