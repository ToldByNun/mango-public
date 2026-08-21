from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mango_tools.format import TOOL_CALL_PREFIX

# Applied only AFTER TOOL_CALL_PREFIX. Flat JSON strings only — cheaper token masks.
_PAYLOAD_GBNF = r"""
string ::= "\"" char* "\""
char   ::= [^"\\] | "\\" (["\\] | "n" | "t" | "/")
ws     ::= [ \t]*
"""

_WRITE_FILE_GBNF = r"""
write-file-full ::= "write_file" " : " write-file-obj ">" "\n" "```" "\n" write-raw "```"
write-file-obj ::= "{" ws "\"path\"" ":" ws string ws "}"
write-raw ::= wr-char{24,}
wr-char ::= [^`] | "`" [^`] | "``" [^`]
"""

_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "read_file": ("path",),
    "write_file": ("path",),
    "edit_file": ("path", "old_string", "new_string"),
    "edit_symbol": ("path", "symbol", "body"),
    "rename_symbol": ("old_name", "new_name"),
    "search_code": ("pattern",),
    "codebase_lookup": ("query",),
    "ask_epistemic": ("question",),
    "declare_apis": ("libraries",),
    "run_terminal_command": ("command",),
    "measure": ("command",),
    "run_tests": (),
}


def tool_call_gbnf(
    tool_names: Sequence[str],
    *,
    allow_final_answer: bool = False,
    allow_multiple: bool = False,
    schemas: Sequence[Any] | None = None,
) -> str:
    """GBNF for the bytes after `<tool_call=`. Thought stays unconstrained.

    write_file uses a markdown fence after the JSON path so file bodies are
    raw Python (real newlines), not a JSON-escaped string that truncates.
    """
    del allow_final_answer
    names = [name for name in tool_names if name and name.replace("_", "").isalnum()]
    required = _required_map(schemas)
    required["write_file"] = ("path",)
    if not names:
        names = ["read_file"]

    alts: list[str] = []
    rules: list[str] = []
    include_write_file = False
    for name in names:
        if name == "write_file":
            alts.append("write-file-full")
            include_write_file = True
            continue
        keys = required.get(name, _REQUIRED_KEYS.get(name, ()))
        rule = name.replace("_", "-")
        alts.append(f'({rule}-call ">")')
        rules.append(_call_and_object_rules(name, rule, keys))

    extra = ""
    if allow_multiple:
        extra = rf' ([ \t\n]+ "{TOOL_CALL_PREFIX}" ({" | ".join(alts)}) )*'

    if not alts:
        alts = ['(read-file-call ">")']
        rules.append(_call_and_object_rules("read_file", "read-file", ("path",)))

    parts = [
        f'root ::= ({" | ".join(alts)}){extra}',
        *rules,
    ]
    if include_write_file:
        parts.append(_WRITE_FILE_GBNF.strip())
    parts.append(_PAYLOAD_GBNF.strip())
    return "\n".join(parts) + "\n"


def _required_map(schemas: Sequence[Any] | None) -> dict[str, tuple[str, ...]]:
    mapping = dict(_REQUIRED_KEYS)
    if not schemas:
        return mapping
    for schema in schemas:
        name = getattr(schema, "name", None)
        keys = getattr(schema, "required", None)
        if name and keys is not None and str(name) != "write_file":
            mapping[str(name)] = tuple(str(key) for key in keys)
    return mapping


def _call_and_object_rules(name: str, rule: str, keys: Sequence[str]) -> str:
    obj = f"{rule}-obj"
    call = f'{rule}-call ::= "{name}" " : " {obj}'
    if not keys:
        obj_def = f'{obj} ::= "{{" ws "}}"'
    else:
        pairs = ' "," ws '.join(f'"\\"{key}\\"" ":" ws string' for key in keys)
        obj_def = f'{obj} ::= "{{" ws {pairs} ws "}}"'
    return f"{call}\n{obj_def}"
