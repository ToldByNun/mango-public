from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mango_cot.types import ReasoningNeed, ReasoningState

COMPLEX_KEYWORDS = (
    "refactor",
    "architect",
    "architecture",
    "debug",
    "investigate",
    "implement",
    "migrate",
    "redesign",
    "multi-step",
    "multi step",
    "why",
    "root cause",
    "plan",
)

_NUMBERED_STEP = re.compile(r"(?m)^\s*\d+[\.\)]\s+\S")
_GOAL_FILE = re.compile(
    r"(?i)\b(?:[\w.-]+[/\\])*[\w.-]+\.(?:py|ts|tsx|js|jsx|rs|go|java|rb|cs|kt|swift|txt|csv|md|json|yaml|yml)\b"
)
_GOAL_FUNC_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_GOAL_NAMED = re.compile(
    r"(?i)\b(?:def|class|function|funktion|symbol)\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"|\b([A-Za-z_][A-Za-z0-9_]*)\s+function\b"
)
_GOAL_STOPWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "return",
        "print",
        "len",
        "str",
        "int",
        "list",
        "dict",
        "range",
        "assert",
        "super",
        "type",
        "set",
        "tuple",
        "bool",
        "float",
        "bytes",
        "and",
        "or",
        "not",
        "in",
        "is",
        "lambda",
        "with",
        "as",
        "from",
        "import",
        "def",
        "class",
        "try",
        "except",
        "raise",
        "yield",
        "async",
        "await",
        "max",
        "min",
        "sum",
        "open",
        "format",
        "isinstance",
        "getattr",
        "setattr",
        "enumerate",
        "zip",
        "map",
        "filter",
        "any",
        "all",
        "sorted",
        "reversed",
        "abs",
        "round",
        "id",
        "hash",
        "repr",
        "true",
        "false",
        "none",
        "self",
        "cls",
    }
)


@dataclass(frozen=True)
class GoalTargets:
    symbols: tuple[str, ...] = ()
    files: tuple[str, ...] = ()


def extract_goal_targets(task: str) -> GoalTargets:
    """Collect every file path and callable/named symbol referenced in the goal."""
    text = task or ""
    files: list[str] = []
    seen_files: set[str] = set()
    for match in _GOAL_FILE.finditer(text):
        path = match.group(0).replace("\\", "/")
        key = path.lower()
        if key in seen_files:
            continue
        seen_files.add(key)
        files.append(path)

    symbols: list[str] = []
    seen_symbols: set[str] = set()

    def _add_symbol(name: str | None) -> None:
        if not name:
            return
        lowered = name.lower()
        if lowered in _GOAL_STOPWORDS or lowered in seen_symbols:
            return
        seen_symbols.add(lowered)
        symbols.append(name)

    for match in _GOAL_FUNC_CALL.finditer(text):
        _add_symbol(match.group(1))
    for match in _GOAL_NAMED.finditer(text):
        _add_symbol(match.group(1) or match.group(2))
    return GoalTargets(symbols=tuple(symbols), files=tuple(files))


def classify_reasoning_need(
    task: str,
    context_state: Any,
    reasoning_state: ReasoningState | None = None,
) -> ReasoningNeed:
    """Heuristic: none | short | extended.

    Signals: task complexity, failed tool attempts, open questions.
    Simple one-liners with no failures stay on "none" so the action loop
    does not pay for an extra model call.
    """
    failed = _failed_attempt_count(context_state)
    open_questions = len(getattr(reasoning_state, "open_questions", []) or [])
    score = 0

    text = (task or "").strip()
    lowered = text.lower()
    if len(text) > 220:
        score += 1
    if len(text) > 450:
        score += 1
    steps = len(_NUMBERED_STEP.findall(text))
    if steps >= 3:
        score += 1
    if any(keyword in lowered for keyword in COMPLEX_KEYWORDS):
        score += 1
    if len(getattr(context_state, "relevant_files", []) or []) >= 4:
        score += 1

    score += min(failed, 3)
    score += min(open_questions, 2)

    failed_tests = list(getattr(context_state, "verification_failed_tests", None) or [])
    impl_paths = {
        str(path) for path in (getattr(context_state, "verification_impl_paths", None) or []) if path
    }
    impl_symbols = {
        str(sym) for sym in (getattr(context_state, "verification_impl_symbols", None) or []) if sym
    }
    # E: verification already shows a multi-file / multi-test failure.
    multi_verification = len(failed_tests) >= 2 or len(impl_paths) >= 2 or len(impl_symbols) >= 2
    # Pre-write: the goal itself names multiple files or symbols.
    targets = extract_goal_targets(task)
    goal_multi_target = len(targets.symbols) >= 2 or len(targets.files) >= 2
    collection_error = bool(getattr(context_state, "verification_collection_error", False))

    if (
        multi_verification
        or goal_multi_target
        or collection_error
        or failed >= 2
        or open_questions >= 3
        or score >= 4
    ):
        return ReasoningNeed.EXTENDED
    if failed >= 1 or score >= 2:
        return ReasoningNeed.SHORT
    return ReasoningNeed.NONE


def _failed_attempt_count(context_state: Any) -> int:
    results = getattr(context_state, "tool_results", None) or []
    count = 0
    for entry in results:
        if getattr(entry, "success", True) is False:
            count += 1
            continue
        if isinstance(entry, dict) and not entry.get("success", True):
            count += 1
    return count
