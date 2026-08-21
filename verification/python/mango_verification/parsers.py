from __future__ import annotations

import re

from mango_verification.types import Diagnostic, TestSummary

_PYTEST_FAILED = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)
_PYTEST_ERROR_FILE = re.compile(r"^ERROR\s+(\S+)", re.MULTILINE)
_PYTEST_COLLECTION = re.compile(r"error during collection", re.IGNORECASE)
_IMPORTISH = re.compile(
    r"(SyntaxError|ImportError|ModuleNotFoundError|NameError|IndentationError):\s*.+$",
    re.MULTILINE,
)
_CANNOT_IMPORT = re.compile(
    r"cannot import name ['\"](\w+)['\"](?: from ['\"]([\w.]+)['\"])?",
    re.IGNORECASE,
)
_PYTEST_SUMMARY = re.compile(
    r"(\d+)\s+passed(?:,\s*(\d+)\s+failed)?|(\d+)\s+failed(?:,\s*(\d+)\s+passed)?"
)
_ASSERT = re.compile(r"^(E\s+)?(AssertionError|Error|Exception|assert)\b.*$", re.MULTILINE)
_E_LINE = re.compile(r"^E\s+(.+)$", re.MULTILINE)
_FILE_LINE = re.compile(
    r"^(?P<path>[^\s:]+?\.(?:py|ts|js|rs|go|java|c|cpp|h)):(?P<line>\d+)(?::\d+)?:?\s*(?P<msg>.+)$",
    re.MULTILINE,
)
_GCC = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<sev>error|warning|Error|fatal error):\s*(?P<msg>.+)$",
    re.MULTILINE,
)
_RUFF = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):\d+:\s+(?P<msg>.+)$",
    re.MULTILINE,
)


def parse_test_output(output: str) -> TestSummary:
    failed_names = _PYTEST_FAILED.findall(output)
    passed, failed = _count_pytest(output)
    if failed == 0 and failed_names:
        failed = len(failed_names)
    collection_errors = _collection_files(output)
    errors: list[str] = []
    for match in _IMPORTISH.finditer(output):
        line = match.group(0).strip()
        if line and line not in errors:
            errors.append(line)
    for match in _E_LINE.finditer(output):
        line = match.group(1).strip()
        if line and line not in errors:
            errors.append(line)
    for match in _ASSERT.finditer(output):
        line = match.group(0).strip().lstrip("E ").strip()
        if line and line not in errors:
            errors.append(line)
    if not errors:
        for match in _FILE_LINE.finditer(output):
            msg = match.group("msg").strip()
            if "Error" in msg or "assert" in msg.lower():
                errors.append(f"{match.group('path')}:{match.group('line')}: {msg}")
    for raw in _PYTEST_FAILED.finditer(output):
        line = raw.group(0).strip()
        if " - " in line:
            detail = line.split(" - ", 1)[1].strip()
            if detail and detail not in errors:
                errors.append(detail)
    return TestSummary(
        passed=passed,
        failed=failed,
        failed_names=failed_names[:20],
        errors=errors[:12],
        collection_errors=collection_errors[:8],
    )


def _collection_files(output: str) -> list[str]:
    files = [match.group(1) for match in _PYTEST_ERROR_FILE.finditer(output)]
    if not files:
        files = re.findall(r"ERROR collecting\s+(\S+)", output)
    if files:
        seen: list[str] = []
        for path in files:
            if path not in seen:
                seen.append(path)
        return seen
    if _PYTEST_COLLECTION.search(output):
        return ["(collection)"]
    return []


def parse_diagnostics(output: str, *, default_severity: str = "error") -> list[Diagnostic]:
    found: list[Diagnostic] = []
    seen: set[str] = set()
    for pattern in (_GCC, _RUFF, _FILE_LINE):
        for match in pattern.finditer(output):
            path = match.groupdict().get("path")
            line_s = match.groupdict().get("line")
            msg = (match.groupdict().get("msg") or match.group(0)).strip()
            sev = match.groupdict().get("sev") or default_severity
            key = f"{path}:{line_s}:{msg}"
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Diagnostic(
                    message=msg[:300],
                    path=path,
                    line=int(line_s) if line_s else None,
                    severity=str(sev).lower(),
                )
            )
    return found[:40]


def _count_pytest(output: str) -> tuple[int, int]:
    match = _PYTEST_SUMMARY.search(output.replace("\n", " "))
    if not match:
        # last-line style: "1 failed, 2 passed in 0.12s"
        tail = output.strip().splitlines()[-1] if output.strip() else ""
        match = _PYTEST_SUMMARY.search(tail)
    if not match:
        return 0, 0
    if match.group(1) is not None:
        passed = int(match.group(1))
        failed = int(match.group(2) or 0)
        return passed, failed
    failed = int(match.group(3) or 0)
    passed = int(match.group(4) or 0)
    return passed, failed


def parse_missing_import(text: str) -> tuple[str, str] | None:
    """Return (symbol, module) when importlib reports a missing name."""
    match = _CANNOT_IMPORT.search(text or "")
    if not match:
        return None
    return match.group(1), match.group(2) or ""
