"""install_packages — pip install with UI confirm."""

from __future__ import annotations

from typing import Any

from mango_epistemic.install_deps import ensure_packages
from mango_tools.confirm_gate import request_confirm


def install_packages(
    packages: str,
    *,
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Install missing third-party packages into the current Python (after confirm)."""
    names = [p.strip() for p in str(packages or "").replace(";", ",").split(",") if p.strip()]
    if not names:
        return {"ok": False, "error": "empty_packages"}
    # Cap spam
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
    summary = f"Install Python packages: {', '.join(uniq)}"
    allowed = request_confirm(
        summary=summary,
        kind="pip",
        detail=f"python -m pip install {' '.join(uniq)}",
    )
    if not allowed:
        return {"ok": False, "error": "user_denied", "packages": uniq}
    result = ensure_packages(uniq, timeout=240)
    result["confirmed"] = True
    return result


def register_install_packages(registry: Any) -> None:
    registry.register(
        "install_packages",
        install_packages,
        description=(
            "Install missing PyPI packages (pip) after the user confirms a popup. "
            "Use when ask_epistemic / imports fail with ModuleNotFoundError."
        ),
        parameters={
            "packages": {
                "type": "string",
                "description": "Comma-separated import or pip names e.g. discord.py, httpx",
            }
        },
        required=["packages"],
    )
