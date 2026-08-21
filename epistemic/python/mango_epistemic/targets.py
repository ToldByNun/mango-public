from __future__ import annotations

import re
from typing import Any, Iterable

_DOT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SKIP_DOT = frozenset({"e", "i", "eg", "ie"})

_ALIAS = {
    "deque": ("collections", "deque"),
    "namedtuple": ("collections", "namedtuple"),
    "defaultdict": ("collections", "defaultdict"),
    "lock": ("threading", "Lock"),
    "rlock": ("threading", "RLock"),
    "thread": ("threading", "Thread"),
    "monotonic": ("time", "monotonic"),
    "argumentparser": ("argparse", "ArgumentParser"),
    "path": ("pathlib", "Path"),
    "dumps": ("json", "dumps"),
    "loads": ("json", "loads"),
    "read_csv": ("pandas", "read_csv"),
    "threadpoolexecutor": ("concurrent.futures", "ThreadPoolExecutor"),
}

_MODULE_DEFAULTS: dict[str, list[tuple[str, str]]] = {
    "collections": [("collections", "deque")],
    "threading": [("threading", "Lock")],
    "time": [("time", "monotonic")],
    "argparse": [("argparse", "ArgumentParser")],
    "pathlib": [("pathlib", "Path")],
    "pandas": [("pandas", "read_csv")],
        "json": [("json", "dumps")],
        "csv": [("csv", "DictReader")],
        "concurrent": [("concurrent.futures", "ThreadPoolExecutor")],
        "futures": [("concurrent.futures", "ThreadPoolExecutor")],
        "os": [("os", "path")],
    "sys": [("sys", "argv")],
    "re": [("re", "compile")],
    "asyncio": [("asyncio", "Lock")],
}


def lookup_targets(question: str, *, limit: int = 6) -> list[tuple[str, str]]:
    """Concrete (package, symbol) pairs the API sub-agent must look up before finishing."""
    blob = question or ""
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(package: str, symbol: str) -> None:
        key = (package, symbol)
        if not package or key in seen:
            return
        seen.add(key)
        found.append(key)

    for package, symbol in _DOT.findall(blob):
        if package.lower() in _SKIP_DOT:
            continue
        if package.lower() == "concurrent" and symbol.lower() == "futures":
            add("concurrent.futures", "ThreadPoolExecutor")
            continue
        add(package, symbol)

    words = _WORD.findall(blob)
    for word in words:
        alias = _ALIAS.get(word.lower())
        if alias:
            add(*alias)
    for word in words:
        for item in _MODULE_DEFAULTS.get(word.lower()) or []:
            add(*item)
    return found[:limit]


def output_covers(output: dict[str, Any], target: tuple[str, str]) -> bool:
    package, symbol = target
    got_package = str(output.get("package") or output.get("library") or "").strip()
    got_symbol = str(output.get("symbol") or "").strip()
    qual = str(output.get("qualname") or "").strip().lower()
    want = f"{package}.{symbol}".lower() if symbol else package.lower()
    if qual == want or (symbol and qual.endswith("." + symbol.lower())):
        return True
    if got_package.lower() != package.lower():
        return False
    if not symbol:
        return True
    return got_symbol.lower() == symbol.lower() or got_symbol.lower().endswith("." + symbol.lower())


def missing_targets(
    outputs: Iterable[Any],
    targets: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    covered: set[tuple[str, str]] = set()
    for output in outputs:
        if not isinstance(output, dict):
            continue
        for target in targets:
            if output_covers(output, target):
                covered.add(target)
    return [target for target in targets if target not in covered]
