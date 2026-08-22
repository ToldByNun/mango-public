"""Static checks that an implementation matches the goal before the agent may finish."""

from __future__ import annotations

import ast
import re

_MAIN_GUARD = re.compile(r'if\s+__name__\s*==\s*["\']__main__["\']')

_GOAL_WANTS_RUNNABLE = re.compile(
    r"(?i)\b("
    r"cli|command[- ]line|console|konsole|terminal|über die konsole|"
    r"runs? from (?:the )?console|subcommand|entrypoint|entry point|"
    r"python projekt|python project|script you can run|ausführbar"
    r")\b"
)

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
        re.compile(r"(?i)\b(update|updaten|ändern|aktualisieren|bearbeiten|count)\b"),
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
)


def goal_wants_runnable_script(task: str) -> bool:
    return bool(_GOAL_WANTS_RUNNABLE.search(task or ""))


def required_features(task: str) -> list[str]:
    """Human labels for capabilities the goal text asks for."""
    if not task.strip():
        return []
    labels: list[str] = []
    for goal_pat, _code_pat, label in _FEATURE_HINTS:
        if goal_pat.search(task) and label not in labels:
            labels.append(label)
    return labels


def summarize_impl_status(source: str, task: str = "", *, path: str = "") -> str:
    """Content-based snapshot for the prompt — never byte size."""
    text = source or ""
    header = path.strip() or "module"
    line_count = len(text.splitlines())
    lines = [f"{header}: {line_count} lines of source"]

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

    lines.append(
        f"__main__ entry: {'present' if _MAIN_GUARD.search(text) else 'MISSING'}"
    )
    if "ArgumentParser(" in text:
        lines.append(
            f"argparse wired: {'yes' if 'parse_args(' in text else 'NO — parse_args() missing'}"
        )

    needed = required_features(task)
    if needed:
        lines.append(f"Goal requires: {', '.join(needed)}")

    gaps = find_impl_gaps(text, task)
    if gaps:
        lines.append("Still missing / incomplete:")
        for gap in gaps[:10]:
            lines.append(f"  - {gap}")
    else:
        lines.append("Static completeness: OK")

    return "\n".join(lines)


def find_impl_gaps(source: str, task: str = "") -> list[str]:
    """Return human-readable reasons the module is not shippable yet."""
    text = source or ""
    gaps: list[str] = []
    if not text.strip():
        return ["File is empty"]

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"Syntax error: {exc.msg} (line {exc.lineno or '?'})"]

    if goal_wants_runnable_script(task):
        gaps.extend(_cli_entry_gaps(text, task))
        gaps.extend(_goal_feature_gaps(text, task))

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and _function_looks_incomplete(node):
            gaps.append(f"Function `{node.name}` looks incomplete (stub body — finish the logic)")

    return _dedupe(gaps)


def _cli_entry_gaps(source: str, task: str = "") -> list[str]:
    gaps: list[str] = []
    if not _MAIN_GUARD.search(source):
        gaps.append("Missing `if __name__ == '__main__'` entry point")
    uses_argparse = "import argparse" in source or "from argparse" in source or "ArgumentParser(" in source
    if uses_argparse:
        if "ArgumentParser(" not in source:
            gaps.append("argparse imported but no ArgumentParser() created")
        elif "parse_args(" not in source:
            gaps.append("ArgumentParser exists but parse_args() was never called")
        elif required_features(task) and "add_subparsers" not in source and "add_parser(" not in source:
            gaps.append("CLI needs argparse subcommands (add_subparsers/add_parser) for each goal action")
    return gaps


def _goal_feature_gaps(source: str, task: str) -> list[str]:
    if not task.strip():
        return []
    lower = source.lower()
    gaps: list[str] = []
    for goal_pat, code_pat, label in _FEATURE_HINTS:
        if goal_pat.search(task) and not code_pat.search(lower):
            gaps.append(f"Goal needs {label} behavior but no matching function/command in code")
    return gaps


def _function_looks_incomplete(node: ast.FunctionDef) -> bool:
    name = node.name
    if name.startswith("test_") or name in {"setUp", "tearDown"}:
        return False
    body = node.body
    if not body:
        return True
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True
    if any(_stmt_is_substantive(stmt) for stmt in body):
        return False
    assigns = [stmt for stmt in body if isinstance(stmt, ast.Assign)]
    if len(body) == 1 and len(assigns) == 1:
        return True
    if len(body) >= 2:
        return False
    return True


def _stmt_is_substantive(stmt: ast.AST) -> bool:
    if isinstance(stmt, (ast.Return, ast.Raise, ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Match)):
        return True
    if isinstance(stmt, ast.Expr):
        value = stmt.value
        if isinstance(value, ast.Call):
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
