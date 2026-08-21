from __future__ import annotations

import warnings
from pathlib import Path


def python_syntax_error(path: str | Path, source: str | None = None) -> str | None:
    """Return a compact SyntaxError for a .py file, or None if it parses. Does not execute code."""
    file_path = Path(path)
    if file_path.suffix != ".py":
        return None
    if source is None:
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError:
            return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            compile(source, str(file_path), "exec")
    except SyntaxError as exc:
        line = exc.lineno or 0
        loc = f"{file_path.name}:{line}" if line else file_path.name
        detail = f"{loc}: {exc.msg or 'invalid syntax'}"
        text = (exc.text or "").strip()
        if text:
            detail += f"\n  {text}"
        return detail
    return None


def salvage_python_source(source: str) -> str | None:
    """Drop trailing incomplete lines until `compile()` succeeds."""
    if python_syntax_error("salvage.py", source=source) is None:
        return source
    lines = source.splitlines()
    while lines:
        lines.pop()
        candidate = "\n".join(lines).rstrip() + "\n"
        if len(candidate.strip()) < 20:
            return None
        if python_syntax_error("salvage.py", source=candidate) is None:
            return candidate
    return None


def collect_python_syntax_errors(paths: list[str | Path]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for path in paths:
        err = python_syntax_error(path)
        if err and err not in seen:
            seen.add(err)
            errors.append(err)
    return errors
