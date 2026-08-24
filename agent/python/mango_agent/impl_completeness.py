"""Goal-driven checks that an implementation matches before the agent may finish.

Entry-point rules are selected from the file language (path / content / goal),
not a hardcoded Python ``__main__`` string in the agent loop.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

_GOAL_WANTS_RUNNABLE = re.compile(
    r"(?i)\b("
    r"cli|command[- ]line|console|konsole|terminal|über die konsole|"
    r"runs? from (?:the )?console|subcommand|entrypoint|entry point|"
    r"python projekt|python project|script you can run|ausführbar|"
    r"\bbot\b|discord|service that listens"
    r")\b"
)

_REPO_PATCH_GOAL = re.compile(
    r"(?i)fix the following github issue|minimal code changes needed to resolve|"
    r"failing tests \(use these to locate"
)


def is_repo_patch_goal(task: str) -> bool:
    """SWE-bench / existing-repo patch goals — not greenfield CLI completeness."""
    return bool(_REPO_PATCH_GOAL.search(task or ""))

# Bare "|count|" must NOT match "Counts word frequency" CLI goals.
_FEATURE_HINTS: tuple[tuple[re.Pattern[str], re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)\b(add|hinzufügen|hinzuzufügen|einfügen|anlegen)\b"),
        re.compile(r"(?i)\b(add|insert|create)[_\w]*"),
        "add/create items",
    ),
    (
        re.compile(r"(?i)\b(remove|delete|löschen|entfernen|removen)\b"),
        re.compile(r"(?i)\b(remove|delete)[_\w]*"),
        "remove items",
    ),
    (
        re.compile(
            r"(?i)\b(update|updaten|ändern|aktualisieren|bearbeiten|item count|stückzahl|stueckzahl)\b"
        ),
        re.compile(r"(?i)\b(update|set|change)[_\w]*"),
        "update item count",
    ),
    (
        re.compile(r"(?i)\b(beschreibung|beschreibungen|description)\b"),
        re.compile(r"(?i)\b(description|desc\b|[\"']description[\"'])"),
        "item descriptions",
    ),
    (
        re.compile(r"(?i)\b(list|anzeigen|auflisten|show|inventory)\b"),
        re.compile(r"(?i)\b(list|show|print)[_\w]*"),
        "list/show inventory",
    ),
    # Integration goals (Discord→LM Studio, webhooks, etc.): require real call sites.
    (
        re.compile(
            r"(?i)\b(lm studio|openai|localhost:\d+|gpt[- ]style|/v1/chat|"
            r"http\s+api|rest\s+api|api\s+call)\b"
        ),
        re.compile(
            r"(?i)(requests\.|httpx\.|aiohttp\.|urllib\.request|"
            r"fetch\(|openai\.|/v1/chat|chat/completions)"
        ),
        "HTTP/API call to the model host",
    ),
    (
        re.compile(
            r"(?i)\b(send (?:back|the output)|posts? (?:the |it back)|"
            r"reply (?:with|to)|responds? with|as a new message)\b"
        ),
        re.compile(
            r"(?i)(\.send\(|\.reply\(|channel\.send|send_message|"
            r"create_message|post_message)"
        ),
        "send/reply with the model output",
    ),
    (
        re.compile(
            r"(?i)\b(waits? for messages|listens? for messages|"
            r"on[_ ]message|when a message is received)\b"
        ),
        re.compile(r"(?i)(on_message|message_create|message\.content|event.*message)"),
        "message receive handler",
    ),
)

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
}

_GOAL_LANG_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(?:^|[^a-z0-9_])(c\+\+|cpp|cplusplus)(?:[^a-z0-9_]|$)"), "cpp"),
    (re.compile(r"(?i)(?:^|[^a-z0-9_+.])c(?:[^a-z0-9_+.]|$)|\.c\b"), "c"),
    (re.compile(r"(?i)\b(golang|go)\b|\.go\b"), "go"),
    (re.compile(r"(?i)\b(rust)\b|\.rs\b"), "rust"),
    (re.compile(r"(?i)\b(typescript)\b|\.ts\b"), "typescript"),
    (re.compile(r"(?i)\b(javascript|nodejs|node\.js)\b|\.js\b"), "javascript"),
    (re.compile(r"(?i)\b(python)\b|\.py\b"), "python"),
)


@dataclass(frozen=True)
class EntryPointRule:
    """Language-specific runnable entry detector."""

    language: str
    label: str
    pattern: re.Pattern[str]


# Ordered registry — first match for a language wins.
_ENTRY_RULES: dict[str, EntryPointRule] = {
    "python": EntryPointRule(
        "python",
        "if __name__ == '__main__'",
        re.compile(r"""if\s+__name__\s*==\s*['\"]__main__['\"]"""),
    ),
    "c": EntryPointRule(
        "c",
        "int main(...)",
        re.compile(r"\bint\s+main\s*\("),
    ),
    "cpp": EntryPointRule(
        "cpp",
        "int main(...)",
        re.compile(r"\bint\s+main\s*\("),
    ),
    "go": EntryPointRule(
        "go",
        "func main()",
        re.compile(r"\bfunc\s+main\s*\("),
    ),
    "rust": EntryPointRule(
        "rust",
        "fn main()",
        re.compile(r"\bfn\s+main\s*\("),
    ),
    "javascript": EntryPointRule(
        "javascript",
        "require.main === module (or top-level CLI)",
        re.compile(
            r"require\.main\s*===\s*module|import\.meta\.url|process\.argv",
            re.I,
        ),
    ),
    "typescript": EntryPointRule(
        "typescript",
        "CLI entry (import.meta / process.argv)",
        re.compile(r"import\.meta\.url|process\.argv", re.I),
    ),
}


def goal_wants_runnable_script(task: str) -> bool:
    return bool(_GOAL_WANTS_RUNNABLE.search(task or ""))


def required_features(task: str) -> list[str]:
    """Human labels for capabilities the goal text asks for."""
    if not (task or "").strip():
        return []
    labels: list[str] = []
    for goal_pat, _code_pat, label in _FEATURE_HINTS:
        if goal_pat.search(task) and label not in labels:
            labels.append(label)
    return labels


def _language_from_goal(goal: str) -> str:
    text = goal or ""
    if not text.strip():
        return ""
    for pattern, lang in _GOAL_LANG_HINTS:
        if pattern.search(text):
            return lang
    return ""


def detect_language(path: str = "", source: str = "", *, goal: str = "") -> str:
    """Infer language from path extension, then content, then goal hints."""
    suffix = Path(path or "").suffix.lower()
    if suffix in _EXT_TO_LANG:
        return _EXT_TO_LANG[suffix]
    text = source or ""
    if re.search(r"^\s*def\s+\w+\s*\(", text, re.M) or "import " in text[:400]:
        if _ENTRY_RULES["python"].pattern.search(text) or "def " in text:
            return "python"
    if re.search(r"\bint\s+main\s*\(", text):
        return "cpp" if ("std::" in text or "#include <iostream>" in text) else "c"
    if re.search(r"\bfunc\s+main\s*\(", text):
        return "go"
    if re.search(r"\bfn\s+main\s*\(", text):
        return "rust"
    goal_lang = _language_from_goal(goal)
    if goal_lang:
        return goal_lang
    return "python"


def entry_rule_for(path: str = "", source: str = "", *, goal: str = "") -> EntryPointRule | None:
    lang = detect_language(path, source, goal=goal)
    return _ENTRY_RULES.get(lang)


def expected_entry_label(path: str = "", source: str = "", *, goal: str = "") -> str:
    """Human label for the entry point this language/goal expects."""
    rule = entry_rule_for(path, source, goal=goal)
    return rule.label if rule is not None else "language-appropriate entry point"


def has_entry_point(source: str, *, path: str = "", goal: str = "") -> bool:
    rule = entry_rule_for(path, source, goal=goal)
    if rule is None:
        return True
    return bool(rule.pattern.search(source or ""))


def summarize_impl_status(source: str, task: str = "", *, path: str = "") -> str:
    """Content-based snapshot for the prompt — never byte size."""
    text = source or ""
    header = path.strip() or "module"
    lang = detect_language(path, text, goal=task)
    line_count = len(text.splitlines())
    lines = [f"{header}: {line_count} lines of source ({lang})"]

    if lang == "python":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            lines.append(f"Syntax: BROKEN ({exc.msg} at line {exc.lineno or '?'})")
            return "\n".join(lines)

        funcs = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        if funcs:
            lines.append(f"Functions: {', '.join(funcs)}")
        else:
            lines.append("Functions: (none)")
        if classes:
            lines.append(f"Classes: {', '.join(classes)}")
        if "ArgumentParser(" in text:
            lines.append(
                f"argparse wired: {'yes' if 'parse_args(' in text else 'NO — parse_args() missing'}"
            )

    rule = entry_rule_for(path, text, goal=task)
    if rule is not None and goal_wants_runnable_script(task):
        present = bool(rule.pattern.search(text))
        lines.append(f"Entry point ({rule.label}): {'present' if present else 'MISSING'}")

    needed = required_features(task)
    if needed and not is_repo_patch_goal(task):
        lines.append(f"Goal requires: {', '.join(needed)}")

    gaps = find_impl_gaps(text, task, path=path) if not is_repo_patch_goal(task) else []
    if gaps:
        lines.append("Still missing / incomplete:")
        for gap in gaps[:10]:
            lines.append(f"  - {gap}")
    else:
        lines.append("Static completeness: OK")

    return "\n".join(lines)


def looks_truncated_source(source: str) -> bool:
    """Heuristics for mid-generation cutoffs that still parse as valid Python."""
    text = (source or "").rstrip()
    if not text:
        return True
    last = text.splitlines()[-1].strip()
    if not last:
        return True
    # Lone dangling comment / ellipsis left by a truncated write.
    if last in {"#", "...", "…", "\\", "pass #"}:
        return True
    if re.fullmatch(r"#\s*", last) or re.fullmatch(r"#\s*\.{2,}", last):
        return True
    # Trailing unfinished operators / open call often survive broken fences.
    if re.search(r"[,(\\+\-*/=]\s*$", last) and not last.startswith("#"):
        return True
    return False


def find_impl_gaps(source: str, task: str = "", *, path: str = "") -> list[str]:
    """Return human-readable reasons the module is not shippable yet."""
    text = source or ""
    if not text.strip():
        return ["File is empty"]

    lang = detect_language(path, text, goal=task)
    gaps: list[str] = []

    if looks_truncated_source(text):
        gaps.append("File looks truncated mid-write (dangling `#` / unfinished line) — rewrite complete file")

    if lang == "python":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return [f"Syntax error: {exc.msg} (line {exc.lineno or '?'})"]
    else:
        tree = None

    # Feature gaps apply to ANY goal that asks for them — not only CLIs.
    # (Discord→LM Studio was finishing hollow because gaps were CLI-gated.)
    gaps.extend(_goal_feature_gaps(text, task))

    if goal_wants_runnable_script(task):
        gaps.extend(_entry_gaps(text, path=path, goal=task))
        if lang == "python":
            gaps.extend(_python_cli_wiring_gaps(text, task))
            gaps.extend(_bot_entry_gaps(text, task))
            gaps.extend(_discord_quality_gaps(text, task))

    if tree is not None:
        for name in _incomplete_python_defs(tree):
            gaps.append(
                f"Function `{name}` looks incomplete (stub / early-return only — finish the logic)"
            )

    return _dedupe(gaps)


def _bot_entry_gaps(source: str, task: str) -> list[str]:
    if not re.search(r"(?i)\bbot\b|discord", task or ""):
        return []
    if re.search(r"""if\s+__name__\s*==\s*['\"]__main__['\"]""", source):
        return []
    if re.search(r"(?i)\.run\s*\(", source):
        return []
    return ["Missing bot start (`Client.run` / `bot.run` under `__main__`)"]


def _discord_quality_gaps(source: str, task: str) -> list[str]:
    """Structural Discord/LM-Studio wiring bugs that superficial token checks miss."""
    if not re.search(r"(?i)\bdiscord\b|\bbot\b", task or ""):
        return []
    if "discord" not in (source or "").lower():
        return []
    gaps: list[str] = []
    text = source or ""

    # Mashed rewrite / insert collision: duplicate imports or glued comments.
    if text.count("import discord") >= 2 or text.count("import requests") >= 2:
        gaps.append(
            "File looks mashed (duplicate imports) — rewrite ONE clean complete file with write_file"
        )
    if re.search(r"#[^\n]{0,60}#\s*---", text):
        gaps.append(
            "File looks mashed (glued comments) — rewrite ONE clean complete file with write_file"
        )

    # Sync message handler cannot await Discord I/O.
    if re.search(r"(?m)^def\s+on_message\s*\(", text) and not re.search(
        r"(?m)^async\s+def\s+on_message\s*\(", text
    ):
        gaps.append(
            "on_message must be `async def` (discord.py event) — sync handlers cannot await send"
        )

    # Fake-async send (the generated anti-pattern).
    if "add_done_callback" in text and re.search(r"\.send\s*\(", text):
        gaps.append(
            "Do not fake-async `.send()` with add_done_callback — use `await channel.send(...)` "
            "inside `async def on_message`"
        )

    # Any .send/.reply without await anywhere in the file is almost always wrong for discord.py.
    if re.search(r"\.(?:send|reply)\s*\(", text) and not re.search(
        r"await\s+[^\n]*\.(?:send|reply)\s*\(", text
    ):
        gaps.append(
            "Missing `await` on Discord send/reply — handler must `await message.channel.send(...)`"
        )

    # Reading message.content requires privileged intent on modern discord.py.
    if "message.content" in text:
        has_kw = bool(re.search(r"Intents\s*\([^)]*message_content\s*=\s*True", text))
        has_assign = bool(re.search(r"(?<!Intents\.default)\.\s*message_content\s*=\s*True", text))
        bogus = bool(re.search(r"Intents\.default\.message_content\s*=", text))
        if bogus or not (has_kw or has_assign):
            gaps.append(
                "Enable `intents.message_content = True` on the Intents instance passed to "
                "Client (not `Intents.default.message_content = True`)"
            )

    # Event registration: assigning sync function to bot.on_message is a smell when
    # @bot.event async def is the correct pattern — flag if on_message is sync assign.
    if re.search(r"\.on_message\s*=\s*on_message\b", text) and re.search(
        r"(?m)^def\s+on_message\s*\(", text
    ):
        gaps.append(
            "Register the handler with `@bot.event` / `async def on_message` — "
            "do not assign a sync function to bot.on_message"
        )

    return gaps


def _incomplete_python_defs(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _function_looks_incomplete(node):
                found.append(node.name)
    return found


def try_auto_add_entry_point(source: str, task: str = "", *, path: str = "") -> str | None:
    """If the only open gap is a missing entry point and main() exists, append it."""
    gaps = find_impl_gaps(source, task, path=path)
    if not gaps:
        return None
    if not all("entry point" in gap.lower() for gap in gaps):
        return None
    rule = entry_rule_for(path, source, goal=task)
    if rule is None or rule.pattern.search(source or ""):
        return None
    body = (source or "").rstrip() + "\n"
    if rule.language != "python":
        return None
    if not re.search(r"(?m)^def\s+main\s*\(", body):
        return None
    return body + (
        "\nif __name__ == \"__main__\":\n"
        "    raise SystemExit(main())\n"
    )


def try_auto_add_message_content_intent(source: str, task: str = "", *, path: str = "") -> str | None:
    """If the only open Discord gap is message_content intent, inject it."""
    if not re.search(r"(?i)\bdiscord\b", task or ""):
        return None
    text = source or ""
    gaps = find_impl_gaps(text, task, path=path)
    if not gaps:
        return None
    if not all("message_content" in g.lower() for g in gaps):
        return None
    # Strip bogus Intents.default.message_content = ... lines first.
    text = re.sub(
        r"(?m)^[ \t]*discord\.Intents\.default\.message_content\s*=\s*True\s*\n?",
        "",
        text,
    )
    # bot = discord.Client(intents=discord.Intents.default())
    pat = re.compile(
        r"^([ \t]*)(\w+)\s*=\s*discord\.Client\(\s*intents\s*=\s*discord\.Intents\.default\(\)\s*\)\s*$",
        re.M,
    )
    match = pat.search(text)
    if match:
        indent, name = match.group(1), match.group(2)
        block = (
            f"{indent}_intents = discord.Intents.default()\n"
            f"{indent}_intents.message_content = True\n"
            f"{indent}{name} = discord.Client(intents=_intents)"
        )
        return pat.sub(block, text, count=1)
    # intents = discord.Intents.default()
    assign = re.compile(
        r"^([ \t]*)(\w+)\s*=\s*discord\.Intents\.default\(\)\s*$",
        re.M,
    )
    m = assign.search(text)
    if m:
        indent, var = m.group(1), m.group(2)
        if f"{var}.message_content" not in text:
            return text[: m.end()] + f"\n{indent}{var}.message_content = True" + text[m.end() :]
    return None


def _entry_gaps(source: str, *, path: str = "", goal: str = "") -> list[str]:
    rule = entry_rule_for(path, source, goal=goal)
    if rule is None:
        return []
    if rule.pattern.search(source):
        return []
    return [f"Missing entry point: `{rule.label}`"]


def _python_cli_wiring_gaps(source: str, task: str = "") -> list[str]:
    gaps: list[str] = []
    uses_argparse = (
        "import argparse" in source
        or "from argparse" in source
        or "ArgumentParser(" in source
    )
    if not uses_argparse:
        return gaps
    if "ArgumentParser(" not in source:
        gaps.append("argparse imported but no ArgumentParser() created")
    elif "parse_args(" not in source:
        gaps.append("ArgumentParser exists but parse_args() was never called")
    elif required_features(task) and "add_subparsers" not in source and "add_parser(" not in source:
        gaps.append(
            "CLI needs argparse subcommands (add_subparsers/add_parser) for each goal action"
        )
    return gaps


def _goal_feature_gaps(source: str, task: str) -> list[str]:
    if not (task or "").strip():
        return []
    lower = source.lower()
    gaps: list[str] = []
    for goal_pat, code_pat, label in _FEATURE_HINTS:
        if goal_pat.search(task) and not code_pat.search(lower):
            gaps.append(
                f"Goal needs {label} behavior but no matching function/command in code"
            )
    return gaps


def _function_looks_incomplete(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    name = node.name
    if name.startswith("test_") or name in {"setUp", "tearDown", "__init__"}:
        return False
    body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr) or not _is_docstring(stmt)]
    if not body:
        return True
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True
    # Guard-only handler: if author==me: return  — no real work after.
    if _is_hollow_early_return_handler(body):
        return True
    if any(_stmt_is_substantive(stmt) for stmt in body):
        # Still hollow if the only "substantive" bits are early-return guards.
        if _only_early_return_guards(body):
            return True
        return False
    assigns = [stmt for stmt in body if isinstance(stmt, ast.Assign)]
    if len(body) == 1 and len(assigns) == 1:
        return True
    if len(body) >= 2:
        return False
    return True


def _is_docstring(stmt: ast.AST) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_hollow_early_return_handler(body: list[ast.stmt]) -> bool:
    """True when body is only identity/author guards that return, then nothing."""
    if not body:
        return True
    return _only_early_return_guards(body)


def _only_early_return_guards(body: list[ast.stmt]) -> bool:
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.If) and _if_is_early_return_guard(stmt):
            continue
        if isinstance(stmt, ast.Return) and stmt.value is None:
            continue
        # Any real call / loop / assignment / non-guard if → not hollow.
        return False
    return True


def _if_is_early_return_guard(node: ast.If) -> bool:
    """`if x: return` / `if x: return None` with no else body of substance."""
    if node.orelse and not all(isinstance(s, (ast.Pass, ast.Return)) for s in node.orelse):
        # Has a real else branch — treat as logic.
        if any(_stmt_is_substantive(s) and not isinstance(s, ast.Return) for s in node.orelse):
            return False
    body = node.body
    if not body:
        return True
    if all(isinstance(s, (ast.Pass, ast.Return)) for s in body):
        return True
    return False


def _stmt_is_substantive(stmt: ast.AST) -> bool:
    if isinstance(
        stmt, (ast.Return, ast.Raise, ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Match, ast.AsyncWith, ast.AsyncFor)
    ):
        return True
    if isinstance(stmt, ast.Expr):
        value = stmt.value
        if isinstance(value, (ast.Call, ast.Await)):
            return True
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return False
    if isinstance(stmt, ast.Assign):
        return False
    if isinstance(stmt, ast.AugAssign):
        return True
    return False


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
