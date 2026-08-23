from __future__ import annotations

import pytest

from mango_tools.format import TOOL_CALL_PREFIX
from mango_tools.gbnf import tool_call_gbnf
from mango_tools.implementations import create_default_registry
from mango_tools.tool_parser import parse_tool_calls


def test_tool_call_gbnf_is_suffix_after_trigger() -> None:
    names = create_default_registry().list_tools()
    grammar = tool_call_gbnf(names, allow_final_answer=True)
    assert grammar.startswith("root ::= (")
    assert "final ::=" not in grammar
    assert "<tool_call=" not in grammar
    assert "array" not in grammar
    assert r"\u" not in grammar
    for name in names:
        assert f'"{name}"' in grammar
    assert "edit_symbol" in grammar


def test_tool_call_gbnf_requires_declare_apis_keys() -> None:
    grammar = tool_call_gbnf(["declare_apis", "ask_epistemic"])
    assert '"\\"libraries\\""' in grammar
    assert '"\\"question\\""' in grammar
    assert "declare_apis" in grammar


def test_tool_call_gbnf_requires_edit_file_keys() -> None:
    grammar = tool_call_gbnf(["edit_file", "read_file", "edit_symbol"])
    assert '"\\"path\\""' in grammar
    assert '"\\"old_string\\""' in grammar
    assert '"\\"new_string\\""' in grammar
    assert '"\\"symbol\\""' in grammar
    assert '"\\"body\\""' in grammar
    assert "pair   ::= string" not in grammar


def test_tool_call_prefix_is_the_grammar_trigger() -> None:
    assert TOOL_CALL_PREFIX == "<tool_call="


def test_canonical_tool_call_still_parses() -> None:
    text = '<tool_call=edit_symbol : {"path": "a.py", "symbol": "greet", "body": "return 1"}>'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "edit_symbol"
    assert calls[0].arguments["symbol"] == "greet"


def _llama_grammar_cls():
    llama_cpp = pytest.importorskip("llama_cpp")
    grammar_cls = getattr(llama_cpp, "LlamaGrammar", None)
    if grammar_cls is None:
        try:
            from llama_cpp.llama_grammar import LlamaGrammar as grammar_cls
        except ImportError:
            pytest.skip("LlamaGrammar not available")
    return grammar_cls


def test_gbnf_write_file_prefers_fence_with_json_alt() -> None:
    grammar = tool_call_gbnf(["write_file", "read_file"])
    assert "write-file-full" in grammar
    assert "write-file-fence" in grammar
    assert "write-body" in grammar
    assert '"\\"content\\""' in grammar
    assert "content-char{8,500}" in grammar
    grammar = tool_call_gbnf(["edit_symbol", "write_file", "read_file", "rename_symbol"])
    assert grammar.strip().startswith("root ::=")
    assert '">"' in grammar
    assert "rename_symbol" in grammar
    assert '"\\"old_name\\""' in grammar


def test_gbnf_insert_lines_prefers_fence() -> None:
    grammar = tool_call_gbnf(["insert_lines", "edit_file", "read_file"])
    assert "insert-lines-full" in grammar
    assert "insert-lines-fence" in grammar
    assert "write-body" in grammar
    assert "insert-lines-json" in grammar
    # edit_file stays JSON-only (short patches); insert gets the fence path.
    assert "edit-file-call" in grammar or "edit_file" in grammar


def test_gbnf_sole_write_file_is_fence_only() -> None:
    """CODE_REPAIR / CODE_COMPLETE: only write_file → fence body, no JSON content alt."""
    grammar = tool_call_gbnf(["write_file"])
    assert "write-file-fence" in grammar
    assert "write-file-full" not in grammar
    assert "write-file-json" not in grammar
    assert "write-body" in grammar


def test_gbnf_sole_insert_lines_is_fence_only() -> None:
    """CODE_EXTEND: only insert_lines → fence body, no JSON content alt."""
    grammar = tool_call_gbnf(["insert_lines"])
    assert "insert-lines-fence" in grammar
    assert "insert-lines-full" not in grammar
    assert "insert-lines-json" not in grammar
    assert "write-body" in grammar


def test_gbnf_compiles_with_llama_cpp() -> None:
    grammar_cls = _llama_grammar_cls()
    names = create_default_registry().list_tools()
    grammar = tool_call_gbnf(names)
    compiled = grammar_cls.from_string(grammar)
    assert compiled is not None
