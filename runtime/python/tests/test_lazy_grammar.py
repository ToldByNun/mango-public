from __future__ import annotations

from mango_runtime.model_runner import split_completion_budget, stitch_triggered_completion


def test_split_completion_budget_keeps_thought_small() -> None:
    thought, tool = split_completion_budget(512, 96)
    assert thought == 96
    assert tool == 384


def test_split_completion_budget_leaves_room_for_tool() -> None:
    thought, tool = split_completion_budget(64, 96)
    assert thought + tool == 64 or tool >= 32
    assert thought < 64
    assert tool >= 32


def test_split_completion_budget_caps_constrained_tool_tokens() -> None:
    thought, tool = split_completion_budget(4096, 512)
    assert thought == 512
    assert tool == 384


def test_split_completion_budget_respects_tool_max_tokens() -> None:
    thought, tool = split_completion_budget(2048, 192, 1024)
    assert thought == 192
    assert tool == 1024


def test_stitch_triggered_completion_inserts_trigger() -> None:
    text = stitch_triggered_completion("I will edit greet.", "<tool_call=", 'edit_symbol : {"path": "a.py"}>')
    assert text.startswith("I will edit greet.")
    assert "<tool_call=edit_symbol" in text


def test_stitch_triggered_completion_does_not_duplicate_trigger() -> None:
    text = stitch_triggered_completion("plan\n<tool_call=", "<tool_call=", "read_file : {}>")
    assert text.count("<tool_call=") == 1
    assert text.endswith("read_file : {}>")


def test_format_completion_prompt_closes_gemma_thought_channel() -> None:
    from mango_runtime.model_runner import format_completion_prompt

    wrapped = format_completion_prompt("Fix greet.py", model_path="gemma4-coding-Q4_K_M.gguf")
    assert wrapped.startswith("<|turn>user\nFix greet.py")
    assert wrapped.endswith("<|turn>model\n<|channel>thought\n<channel|>")
    again = format_completion_prompt(wrapped, model_path="gemma4-coding-Q4_K_M.gguf")
    assert again == wrapped


def test_format_completion_prompt_skips_non_gemma() -> None:
    from mango_runtime.model_runner import format_completion_prompt

    raw = "Fix greet.py"
    assert format_completion_prompt(raw, model_path="other-model.gguf") == raw
