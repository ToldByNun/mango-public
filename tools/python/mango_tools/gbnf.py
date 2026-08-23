from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mango_tools.format import TOOL_CALL_PREFIX

# Applied only AFTER TOOL_CALL_PREFIX. Flat JSON strings only — cheaper token masks.
_PAYLOAD_GBNF = r"""
string ::= "\"" char* "\""
char   ::= [^"\\] | "\\" (["\\] | "n" | "t" | "/" | "r")
ws     ::= [ \t]*
number ::= [1-9] [0-9]{0,5} | "0"
"""

# Shared fenced body (raw newlines) — used by write_file and insert_lines.
_FENCE_BODY_GBNF = r"""
write-body ::= "```" | wr-char write-body
wr-char ::= [^`] | "`" [^`] | "``" [^`]
"""

# write_file: prefer markdown fence (raw body, real newlines). Recursive write-body so
# the closing ``` is reachable (unlike greedy wr-char{n,}). Short JSON content is an
# alternate for tiny skeletons.
_WRITE_FILE_GBNF = r"""
write-file-full ::= write-file-fence | write-file-json
write-file-fence ::= "write_file" " : " write-file-path ">" "\n" "```" "\n" write-body
write-file-path ::= "{" ws "\"path\"" ":" ws string ws "}"
write-file-json ::= "write_file" " : " write-file-json-obj ">"
write-file-json-obj ::= "{" ws "\"path\"" ":" ws string ws "," ws "\"content\"" ":" ws content-string ws "}"
content-string ::= "\"" content-char{8,500} "\""
content-char ::= [^"\\] | "\\" (["\\] | "n" | "t" | "/" | "r")
"""

# insert_lines: same fence form so the model can add real handler/HTTP blocks,
# not 3-line JSON-escaped nibbles.
_INSERT_LINES_GBNF = r"""
insert-lines-full ::= insert-lines-fence | insert-lines-json
insert-lines-fence ::= "insert_lines" " : " insert-lines-meta ">" "\n" "```" "\n" write-body
insert-lines-meta ::= "{" ws "\"path\"" ":" ws string ws "," ws "\"line\"" ":" ws number ws "}"
insert-lines-json ::= "insert_lines" " : " insert-lines-json-obj ">"
insert-lines-json-obj ::= "{" ws "\"path\"" ":" ws string ws "," ws "\"line\"" ":" ws (number | string) ws "," ws "\"content\"" ":" ws content-string ws "}"
"""

_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "read_file": ("path",),
    "list_dir": (),
    "glob_files": ("pattern",),
    "write_file": ("path",),
    "edit_file": ("path", "old_string", "new_string"),
    "insert_lines": ("path", "line"),
    "delete_file": ("path",),
    "edit_symbol": ("path", "symbol", "body"),
    "rename_symbol": ("old_name", "new_name"),
    "search_code": ("pattern",),
    "codebase_lookup": ("query",),
    "ask_epistemic": ("question",),
    "research_codebase": ("question",),
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

    write_file / insert_lines prefer a markdown fence after the JSON meta so
    bodies use raw newlines. A short JSON ``content`` alternate exists for tiny
    skeletons only.
    """
    del allow_final_answer
    names = [name for name in tool_names if name and name.replace("_", "").isalnum()]
    required = _required_map(schemas)
    required["write_file"] = ("path",)
    required["insert_lines"] = ("path", "line")
    if not names:
        names = ["read_file"]

    alts: list[str] = []
    rules: list[str] = []
    include_write_file = False
    include_insert_lines = False
    # Sole write/insert (CODE_REPAIR / CODE_EXTEND) → fence only, no tiny JSON body.
    sole_write = names == ["write_file"]
    sole_insert = names == ["insert_lines"]
    for name in names:
        if name == "write_file":
            alts.append("write-file-fence" if sole_write else "write-file-full")
            include_write_file = True
            continue
        if name == "insert_lines":
            alts.append("insert-lines-fence" if sole_insert else "insert-lines-full")
            include_insert_lines = True
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
        if sole_write:
            # Fence-only rules for repair/complete (no JSON content alternate).
            parts.append(
                'write-file-fence ::= "write_file" " : " write-file-path ">" "\\n" "```" "\\n" write-body\n'
                'write-file-path ::= "{" ws "\\"path\\"" ":" ws string ws "}"'
            )
        else:
            parts.append(_WRITE_FILE_GBNF.strip())
    if include_insert_lines:
        if sole_insert:
            parts.append(
                'insert-lines-fence ::= "insert_lines" " : " insert-lines-meta ">" "\\n" "```" "\\n" write-body\n'
                'insert-lines-meta ::= "{" ws "\\"path\\"" ":" ws string ws "," ws "\\"line\\"" ":" ws number ws "}"'
            )
        else:
            parts.append(_INSERT_LINES_GBNF.strip())
    if include_write_file or include_insert_lines:
        parts.append(_FENCE_BODY_GBNF.strip())
        # content-string lives in write-file block; insert-lines-json needs it too.
        if include_insert_lines and not include_write_file and not sole_insert:
            parts.append(
                'content-string ::= "\\"" content-char{8,500} "\\""\n'
                'content-char ::= [^"\\\\] | "\\\\" (["\\\\] | "n" | "t" | "/" | "r")'
            )
    parts.append(_PAYLOAD_GBNF.strip())
    return "\n".join(parts) + "\n"


def _required_map(schemas: Sequence[Any] | None) -> dict[str, tuple[str, ...]]:
    mapping = dict(_REQUIRED_KEYS)
    if not schemas:
        return mapping
    for schema in schemas:
        name = getattr(schema, "name", None)
        keys = getattr(schema, "required", None)
        if name and keys is not None and str(name) not in {"write_file", "insert_lines"}:
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
