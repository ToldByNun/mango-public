from __future__ import annotations

from mango_agent.agent import _impl_path_from_pytest, _parse_missing_modules


def test_parse_missing_modules_quoted() -> None:
    text = "E   ModuleNotFoundError: No module named 'discord'\n"
    assert _parse_missing_modules(text) == ["discord"]


def test_parse_missing_modules_nested() -> None:
    text = "No module named 'discord.ext.commands'"
    assert _parse_missing_modules(text) == ["discord"]


def test_parse_missing_modules_empty() -> None:
    assert _parse_missing_modules("AssertionError: expected 1") == []


def test_impl_path_from_pytest_prefers_bot() -> None:
    text = (
        "____________________ test_formula_registered ____________________\n"
        "test_bot.py:12: in test_formula_registered\n"
        "    assert 'formula' in self.bot.commands\n"
        "bot.py:8: in __init__\n"
        "E   AssertionError\n"
    )
    assert _impl_path_from_pytest(text) == "bot.py"


def test_impl_path_from_pytest_skips_test_files() -> None:
    text = "test_bot.py:1: AssertionError\n"
    assert _impl_path_from_pytest(text) is None
