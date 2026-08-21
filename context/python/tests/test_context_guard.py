from __future__ import annotations

from pathlib import Path

from mango_context import ContextBudget, ContextEngine, slice_source


LONG_FN = (
    "PAD = '" + ("Q" * 400) + "'\n\n"
    "def greet(name):\n"
    "    a = 1\n"
    "    b = 2\n"
    "    c = 3\n"
    "    d = 4\n"
    "    e = 5\n"
    "    f = 6\n"
    "    g = 7\n"
    "    return f'hi {name}'\n"
)


def test_slice_source_keeps_signature_and_five_body_lines() -> None:
    sliced = slice_source(LONG_FN, path="util.py", focus_symbols=("greet",))
    assert "def greet(name):" in sliced
    assert sliced.count("a = 1") == 1
    assert "e = 5" in sliced
    assert "f = 6" not in sliced
    assert "g = 7" not in sliced
    assert "more lines" in sliced
    assert "Q" * 50 not in sliced


def test_unfocused_helpers_collapse_to_signature() -> None:
    source = (
        "def keep(x):\n    return x + 1\n\n"
        "def other(y):\n    return y\n    extra = 1\n    extra2 = 2\n"
    )
    sliced = slice_source(source, path="mod.py", focus_symbols=("keep",))
    assert "def keep(x):" in sliced
    assert "return x + 1" in sliced
    assert "def other(y):" in sliced
    assert "extra = 1" not in sliced
    assert "more lines" in sliced


def test_guard_summarizes_old_reads_and_keeps_memory_slice(tmp_path: Path) -> None:
    target = tmp_path / "util.py"
    target.write_text(LONG_FN, encoding="utf-8")
    engine = ContextEngine(
        "Change greet(name) in util.py",
        budget=ContextBudget(max_chars=8_000),
    )
    for i in range(1, 5):
        engine.record_turn(
            i,
            model_output="read",
            tool_results=[
                {
                    "success": True,
                    "tool_name": "read_file",
                    "output": {"path": str(target), "content": LONG_FN},
                }
            ],
        )
    prompt = engine.build_prompt()
    assert "## Memory" in prompt
    assert "def greet(name):" in prompt
    assert "Q" * 50 not in prompt
    assert "[compact]" in prompt
    assert prompt.count("def greet(name):") <= 3
    stored = engine.state.tool_results[0].body
    assert "Q" * 50 not in stored
