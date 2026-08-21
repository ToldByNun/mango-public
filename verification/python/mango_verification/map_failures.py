from __future__ import annotations

import re
from typing import Any

_TEST_TAIL = re.compile(r"(?:.*::)?(test_[A-Za-z0-9_]+|test[A-Z][A-Za-z0-9_]*)")


def symbol_from_test_name(name: str) -> str | None:
    """Map pytest node id / test function name to a likely implementation symbol."""
    text = (name or "").strip()
    if not text:
        return None
    tail = text.split("::")[-1]
    tail = tail.split("[", 1)[0]
    if tail.startswith("test_"):
        rest = tail[5:]
        return rest or None
    if tail.startswith("test") and len(tail) > 4:
        return tail[4:]
    return tail or None


def map_failed_tests(
    failed_names: list[str],
    *,
    codeintel: Any | None = None,
    errors: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Attach implementation path/symbol to each failed test when codeintel can resolve it."""
    mapped: list[dict[str, Any]] = []
    for index, name in enumerate(failed_names):
        symbol = symbol_from_test_name(name)
        impl_path, impl_line = _lookup_impl(codeintel, symbol)
        message = ""
        if errors and index < len(errors):
            message = str(errors[index])
        mapped.append(
            {
                "test_name": name,
                "symbol": symbol,
                "impl_path": impl_path,
                "impl_line": impl_line,
                "message": message,
            }
        )
    return mapped


def _lookup_impl(codeintel: Any | None, symbol: str | None) -> tuple[str | None, int | None]:
    if codeintel is None or not symbol:
        return None, None
    getter = getattr(codeintel, "get_symbol_definition", None)
    if not callable(getter):
        return None, None
    hits = getter(symbol) or []
    if not hits:
        return None, None
    hit = hits[0]
    if isinstance(hit, dict):
        path = hit.get("path")
        line = hit.get("line")
    else:
        path = getattr(hit, "path", None)
        line = getattr(hit, "line", None)
    return (str(path) if path else None, int(line) if line else None)
