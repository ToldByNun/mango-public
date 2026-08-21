from __future__ import annotations

import json

import pytest

from mango_tools.format import format_tool_call
from mango_tools.tool_parser import parse_tool_calls


def test_parse_canonical_format() -> None:
    text = '<tool_call=read_file : {"path": "src/main.py"}>'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments == {"path": "src/main.py"}


def test_parse_multiple_calls() -> None:
    text = (
        'First.\n'
        '<tool_call=read_file : {"path": "a.txt"}>\n'
        'Middle.\n'
        '<tool_call=write_file : {"path": "b.txt", "content": "hi"}>'
    )
    calls = parse_tool_calls(text)
    assert [c.name for c in calls] == ["read_file", "write_file"]
    assert calls[1].arguments["content"] == "hi"


def test_parse_without_space_before_colon() -> None:
    text = '<tool_call=search_code: {"pattern": "foo", "path": "."}>'
    calls = parse_tool_calls(text)
    assert calls[0].name == "search_code"
    assert calls[0].arguments["pattern"] == "foo"


def test_parse_with_extra_whitespace() -> None:
    text = '< tool_call = edit_file  :  {"path": "x.py", "old_string": "a", "new_string": "b"} >'
    calls = parse_tool_calls(text)
    assert calls[0].name == "edit_file"


def test_parse_single_quoted_json() -> None:
    text = "<tool_call=read_file : {'path': 'file.txt'}>"
    calls = parse_tool_calls(text)
    assert calls[0].arguments == {"path": "file.txt"}


def test_parse_nested_json_braces_in_strings() -> None:
    payload = {"content": "const x = { a: 1 };", "path": "out.js"}
    text = format_tool_call("write_file", payload)
    calls = parse_tool_calls(text)
    assert calls[0].arguments == payload


def test_parse_self_closing_suffix() -> None:
    text = '<tool_call=read_file : {"path": "x"} />'
    calls = parse_tool_calls(text)
    assert calls[0].arguments["path"] == "x"


def test_parse_no_calls_returns_empty() -> None:
    assert parse_tool_calls("No tools here.") == []


def test_parse_xml_name_attribute() -> None:
    text = '<tool_call name="read_file"> {"path": "C:/Users/mikaj/Desktop/newtest/test_rate_limiter.py"} </tool_call>'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments["path"].endswith("test_rate_limiter.py")
    assert "</tool_call>" in calls[0].raw


def test_parse_fenced_write_file() -> None:
    text = (
        '<tool_call=write_file : {"path": "event_bus.py"}>\n'
        "```\n"
        "class EventBus:\n"
        "    pass\n"
        "```"
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].arguments["path"] == "event_bus.py"
    assert calls[0].arguments["content"] == "class EventBus:\n    pass\n"


def test_parse_invalid_json_skipped() -> None:
    text = '<tool_call=read_file : {not json}>'
    assert parse_tool_calls(text) == []
