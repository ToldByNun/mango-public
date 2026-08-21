"""Mango Context — Prompt Window / Context Engine."""

from mango_context.ast_slice import slice_source
from mango_context.context_engine import ContextEngine
from mango_context.context_profile import CODER_PROFILE, ContextProfile, DEFAULT_BUDGET
from mango_context.memory import DeterministicMemory, MemoryFact
from mango_context.prompt_window import build_idle_retry_prompt, build_prompt
from mango_context.types import (
    ActionRecord,
    ContextBudget,
    ContextState,
    ToolResultEntry,
    ToolSpec,
    estimate_tokens,
)

__all__ = [
    "ActionRecord",
    "CODER_PROFILE",
    "ContextBudget",
    "ContextEngine",
    "ContextProfile",
    "ContextState",
    "DEFAULT_BUDGET",
    "DeterministicMemory",
    "MemoryFact",
    "ToolResultEntry",
    "ToolSpec",
    "build_idle_retry_prompt",
    "build_prompt",
    "estimate_tokens",
    "slice_source",
]
