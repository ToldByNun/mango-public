"""install_packages — pip install with UI confirm + live console stream."""

from __future__ import annotations

import re
import sys
from typing import Any, Callable

from mango_epistemic.install_deps import ensure_packages
from mango_tools.confirm_gate import request_confirm

_PKG_SPLIT = re.compile(r"[\s,;]+")


def _parse_package_names(packages: str) -> list[str]:
    """Split comma/semicolon/whitespace lists (models often emit 'flask pytest')."""
    names = [p.strip() for p in _PKG_SPLIT.split(str(packages or "")) if p.strip()]
    uniq: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(name)
        if len(uniq) >= 8:
            break
    return uniq


def install_packages(
    packages: str,
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Install missing third-party packages into the current Python (after confirm)."""
    uniq = _parse_package_names(packages)
    if not uniq:
        return {"ok": False, "error": "empty_packages"}
    summary = f"Install Python packages: {', '.join(uniq)}"
    allowed = request_confirm(
        summary=summary,
        kind="pip",
        detail=f"python -m pip install {' '.join(uniq)}",
    )
    if not allowed:
        return {"ok": False, "error": "user_denied", "packages": uniq}

    ctx = _context or {}
    on_line: Callable[[str], None] | None = ctx.get("_on_console_line")
    cancelled = ctx.get("_cancelled")
    cancelled_fn = cancelled if callable(cancelled) else None

    print(
        f"[mango] install_packages confirmed — pip install {' '.join(uniq)} …",
        file=sys.stderr,
        flush=True,
    )
    result = ensure_packages(
        uniq,
        timeout=240,
        on_line=on_line,
        cancelled=cancelled_fn,
    )
    result["confirmed"] = True
    print(
        f"[mango] install_packages done ok={result.get('ok')} "
        f"installed={result.get('installed')} failed={result.get('failed')} "
        f"exit={result.get('exit_code')}",
        file=sys.stderr,
        flush=True,
    )
    return result


def register_install_packages(registry: Any) -> None:
    registry.register(
        "install_packages",
        install_packages,
        description=(
            "Install missing PyPI packages (pip) after the user confirms a popup. "
            "Use when ask_epistemic / imports fail with ModuleNotFoundError. "
            "packages: comma- or space-separated names e.g. flask,pytest or flask pytest."
        ),
        parameters={
            "packages": {
                "type": "string",
                "description": "Comma- or space-separated import/pip names e.g. flask pytest",
            }
        },
        required=["packages"],
    )
