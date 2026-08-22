"""Feature flags for rollback without full git revert.

Each risky behavior change is gated. Defaults match the post-merge "new" behavior
once a phase ships; set the env var to the legacy value to fall back instantly.
"""

from __future__ import annotations

import os
from typing import Literal

ToolFilterMode = Literal["legacy", "complete"]
PromptVariant = Literal["v1", "v2", "ab_test"]
EditMatchMode = Literal["strict_grounded", "grounded_ws"]
StallMode = Literal["off", "soft", "hard"]
ToolProfile = Literal["auto", "tiny", "standard", "full"]

# Recovery-core tools that must never be stripped from GBNF when tools are required
# (A0b complete mode). Nav/delete names are included so A2 can add them without
# changing the filter algorithm again.
RECOVERY_CORE_TOOLS = frozenset(
    {
        "read_file",
        "search_code",
        "list_dir",
        "glob_files",
        "write_file",
        "edit_file",
        "edit_symbol",
        "delete_file",
        "run_tests",
        "run_terminal_command",
    }
)

# Optional tools that tiny profiles may drop from grammar (never recovery-core).
OPTIONAL_TOOLS_TINY = frozenset(
    {
        "measure",
        "web_research",
        "doc_lookup",
        "package_source_lookup",
        "ask_epistemic",
        "declare_apis",
        "codebase_lookup",
        "rename_symbol",
    }
)


def _env(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip() or default


def _truthy(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def tool_filter_mode() -> ToolFilterMode:
    # A0b default: complete (recovery-core always in GBNF). Set legacy to roll back.
    value = _env("MANGO_TOOL_FILTER_MODE", "complete").lower()
    return "legacy" if value == "legacy" else "complete"


def prompt_variant() -> PromptVariant:
    # After A4 A/B non-regression, default to v2; v1 remains loadable forever.
    value = _env("MANGO_PROMPT_VARIANT", "v2").lower()
    if value in {"v1", "ab_test"}:
        return value  # type: ignore[return-value]
    return "v2"


def edit_match_mode() -> EditMatchMode:
    # A3 default: grounded_ws (newline/whitespace tolerant after read).
    value = _env("MANGO_EDIT_MATCH_MODE", "grounded_ws").lower()
    return "strict_grounded" if value == "strict_grounded" else "grounded_ws"


def delete_tool_enabled() -> bool:
    # Default on only when checkpoints are on (A1 before A2 safety).
    raw = os.environ.get("MANGO_DELETE_TOOL")
    if raw is None:
        return file_checkpoints_enabled()
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def file_checkpoints_enabled() -> bool:
    return _truthy("MANGO_FILE_CHECKPOINTS", default=True)


def stall_mode() -> StallMode:
    # A3 default: soft (nudge only; hard stop requires MANGO_STALL_MODE=hard).
    value = _env("MANGO_STALL_MODE", "soft").lower()
    if value in {"off", "hard"}:
        return value  # type: ignore[return-value]
    return "soft"


def apply_patch_enabled() -> bool:
    return _truthy("MANGO_APPLY_PATCH", default=False)


def kv_prefix_reuse_enabled() -> bool:
    return _truthy("MANGO_KV_PREFIX_REUSE", default=True)


def tool_profile() -> ToolProfile:
    value = _env("MANGO_TOOL_PROFILE", "auto").lower()
    if value in {"tiny", "standard", "full"}:
        return value  # type: ignore[return-value]
    return "auto"


def metrics_enabled() -> bool:
    return _truthy("MANGO_METRICS", default=True)


def resolve_tool_profile(*, n_params: int | None = None) -> ToolProfile:
    """Map auto → tiny|standard|full from parameter count when known."""
    profile = tool_profile()
    if profile != "auto":
        return profile
    if n_params is None or n_params <= 0:
        return "standard"
    if n_params <= 8_000_000_000:
        return "tiny"
    if n_params >= 34_000_000_000:
        return "full"
    return "standard"


def flag_snapshot() -> dict[str, str]:
    return {
        "tool_filter_mode": tool_filter_mode(),
        "prompt_variant": prompt_variant(),
        "edit_match_mode": edit_match_mode(),
        "delete_tool": "1" if delete_tool_enabled() else "0",
        "file_checkpoints": "1" if file_checkpoints_enabled() else "0",
        "stall_mode": stall_mode(),
        "apply_patch": "1" if apply_patch_enabled() else "0",
        "kv_prefix_reuse": "1" if kv_prefix_reuse_enabled() else "0",
        "tool_profile": tool_profile(),
        "metrics": "1" if metrics_enabled() else "0",
    }
