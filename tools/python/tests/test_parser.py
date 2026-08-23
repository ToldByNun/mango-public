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


def test_parse_fenced_insert_lines() -> None:
    text = (
        '<tool_call=insert_lines : {"path": "discord_bot.py", "line": 19}>\n'
        "```\n"
        "    resp = requests.post('http://localhost:1234/v1/chat/completions')\n"
        "    await message.channel.send(resp.json()['choices'][0]['message']['content'])\n"
        "\n"
        "bot.run(TOKEN)\n"
        "```"
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "insert_lines"
    assert calls[0].arguments["line"] == 19
    assert "requests.post" in calls[0].arguments["content"]
    assert "bot.run" in calls[0].arguments["content"]


def test_parse_truncated_fence_not_a_write() -> None:
    text = (
        '<tool_call=write_file : {"path": "index.html"}>\n'
        "```\n"
        "<!DOCTYPE html>\n"
        "<html><body>\n"
        "<h1>Hello\n"
    )
    assert parse_tool_calls(text) == []


def test_parse_informal_write_file_pipe() -> None:
    text = (
        'I will create the file.\n'
        '<write_file | {"path": "index.html", "content": "<!DOCTYPE html>\\n<html></html>"}>'
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "write_file"
    assert calls[0].arguments["path"] == "index.html"
    assert "<!DOCTYPE html>" in calls[0].arguments["content"]


def test_parse_invalid_json_skipped() -> None:
    text = '<tool_call=read_file : {not json}>'
    assert parse_tool_calls(text) == []


def test_parse_function_tag_anthropic_style() -> None:
    text = (
        "<tool_call>\n"
        "<function=Read>\n"
        "<parameter=file_path>\n"
        "sales_jan.csv\n"
        "</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments["file_path"] == "sales_jan.csv"


def test_parse_function_tag_bash_alias() -> None:
    text = "<function=Bash>\n<parameter=command>dir</parameter>\n</function>"
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "run_terminal_command"
    assert calls[0].arguments["command"] == "dir"


def test_parse_function_tag_unknown_name_ignored() -> None:
    text = "<function=WebSearch>\n<parameter=query>x</parameter>\n</function>"
    assert parse_tool_calls(text) == []


def test_parse_function_tag_multiple_parameters() -> None:
    text = (
        "<function=Edit>\n"
        "<parameter=file_path>\ncart.py\n</parameter>\n"
        "<parameter=old_string>\nint(s)\n</parameter>\n"
        "<parameter=new_string>\ns\n</parameter>\n"
        "</function>"
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "edit_file"
    assert calls[0].arguments["file_path"] == "cart.py"
    assert calls[0].arguments["old_string"] == "int(s)"
    assert calls[0].arguments["new_string"] == "s"


def test_parse_canonical_still_wins_over_function_tags() -> None:
    text = (
        '<tool_call=read_file : {"path": "main.py"}>\n'
        "<function=Read><parameter=file_path>junk.txt</parameter></function>"
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments["path"] == "main.py"


def test_parse_json_name_format() -> None:
    text = '{"name": "read_file", "arguments": {"path": "inventory.py"}}'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments["path"] == "inventory.py"


def test_parse_loose_tool_prefix() -> None:
    text = 'write_file : {"path": "inventory.py", "content": "print(1)"}'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "write_file"
    assert calls[0].arguments["path"] == "inventory.py"
