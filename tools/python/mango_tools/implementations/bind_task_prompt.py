"""bind_task_prompt — model-authored continuation / sub-agent prompt lock."""

from __future__ import annotations

import re
from typing import Any

_MAX_CHARS = 900
_REQUIRED_ANY = (
    "install_packages",
    "install package",
)
_PERMISSION_ANY = (
    "confirm",
    "permission",
    "popup",
    "allow",
    "deny",
    "user_denied",
)


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def validate_task_prompt(prompt: str) -> dict[str, Any]:
    text = str(prompt or "").strip()
    if not text:
        return {"ok": False, "error": "empty_prompt"}
    if len(text) > _MAX_CHARS:
        return {"ok": False, "error": f"too_long_max_{_MAX_CHARS}", "chars": len(text)}
    if not _has_any(text, _REQUIRED_ANY):
        return {
            "ok": False,
            "error": "must_mention_install_packages",
            "hint": "Include: MUST call install_packages for missing third-party libs (user confirm popup).",
        }
    if not _has_any(text, _PERMISSION_ANY):
        return {
            "ok": False,
            "error": "must_mention_permission_or_confirm",
            "hint": "Include: wait for user Allow/Deny on install_packages / shell.",
        }
    return {"ok": True, "chars": len(text)}


def bind_task_prompt(
    prompt: str,
    *,
    libs: str = "",
    _context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store a short continuation system-prompt fragment for this run."""
    check = validate_task_prompt(prompt)
    if not check.get("ok"):
        return check
    text = str(prompt).strip()
    # Soft-normalize: ensure libs line if provided
    lib_list = [p.strip() for p in str(libs or "").replace(";", ",").split(",") if p.strip()]
    if lib_list and "libs:" not in text.lower() and "libraries:" not in text.lower():
        text = f"Libs: {', '.join(lib_list[:8])}\n{text}"
    store = (_context or {}).get("_bind_task_prompt")
    if callable(store):
        store(text, lib_list)
    return {
        "ok": True,
        "chars": len(text),
        "libs": lib_list,
        "bound": True,
        "prompt_preview": text[:240],
    }


def default_task_prompt(libs: list[str] | None = None) -> str:
    names = ", ".join(libs or []) or "declared third-party libs"
    return (
        f"<task_lock>\n"
        f"Libs: {names}\n"
        f"MUST: if any lib missing locally → install_packages (user confirm popup) "
        f"before write_file. NEVER silent pip. On Deny → web_research/fetch_url then code.\n"
        f"MUST: shell also needs confirm. Prefer install_packages over run_terminal_command for pip.\n"
        f"</task_lock>"
    )


def register_bind_task_prompt(registry: Any) -> None:
    if registry.has("bind_task_prompt"):
        return
    registry.register(
        "bind_task_prompt",
        bind_task_prompt,
        description=(
            "Bind a short continuation/sub-agent system prompt for this run. "
            "MUST mention install_packages + user confirm/permission. "
            "Call after declare_apis, before write_file."
        ),
        parameters={
            "prompt": {
                "type": "string",
                "description": (
                    "Short XML/text system prompt (<900 chars) locking deps install + permission"
                ),
            },
            "libs": {
                "type": "string",
                "description": "Comma-separated libs this lock covers",
                "default": "",
            },
        },
        required=["prompt"],
    )
