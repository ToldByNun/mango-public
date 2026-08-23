from __future__ import annotations

from mango_cli.commands import help_text, parse_slash


def test_parse_plain_goal() -> None:
    parsed = parse_slash("fix the flaky test")
    assert parsed.kind == "plain"
    assert parsed.goal == "fix the flaky test"


def test_parse_ask_mode() -> None:
    parsed = parse_slash("/ask how does login work?")
    assert parsed.kind == "mode"
    assert parsed.mode == "ask"
    assert parsed.goal == "how does login work?"
    assert parsed.display.startswith("/ask")


def test_parse_mode_requires_arg() -> None:
    parsed = parse_slash("/plan")
    assert parsed.kind == "plain"
    assert parsed.goal == ""


def test_parse_local_help() -> None:
    parsed = parse_slash("/help")
    assert parsed.kind == "local"
    assert parsed.command is not None
    assert parsed.command.name == "help"


def test_help_text_lists_modes() -> None:
    text = help_text()
    assert "/ask" in text
    assert "/plan" in text
    assert "send" in text
    assert "newline" in text
