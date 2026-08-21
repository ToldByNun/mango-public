from __future__ import annotations

import pytest

from mango_tools.fuzzy_edit import apply_replace


def test_exact_replace() -> None:
    updated, count, kind = apply_replace("alpha\n", "alpha", "beta")
    assert updated == "beta\n"
    assert count == 1
    assert kind == "exact"


def test_crlf_replace() -> None:
    updated, count, kind = apply_replace("a\r\nb\r\n", "a\nb", "x\ny")
    assert "x\r\ny" in updated
    assert count == 1
    assert kind == "newlines"


def test_trailing_whitespace_replace() -> None:
    content = "def f():\n    return 1\n"
    updated, _count, kind = apply_replace(content, "    return 1  ", "    return 2")
    assert "return 2" in updated
    assert kind == "whitespace"


def test_indent_insensitive_replace() -> None:
    content = "def f():\n\treturn 1\n"
    updated, _count, kind = apply_replace(content, "    return 1", "    return 2")
    assert updated.splitlines()[1] == "\treturn 2"
    assert kind == "indent"


def test_fuzzy_typo_replace() -> None:
    content = "def f():\n    return value\n"
    updated, _count, kind = apply_replace(content, "    retrun value", "    return 9")
    assert "return 9" in updated
    assert kind == "fuzzy"


def test_ambiguous_match_raises() -> None:
    content = "    return value\n    return value\n"
    with pytest.raises(ValueError, match="not found"):
        apply_replace(content, "    retrun value", "    return 2")


def test_missing_still_hints_write_file() -> None:
    with pytest.raises(ValueError, match="write_file"):
        apply_replace("hello\n", "zzzz", "yyyy")
