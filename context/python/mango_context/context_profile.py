from __future__ import annotations

from dataclasses import dataclass

from mango_context.types import ContextBudget


DEFAULT_BUDGET = ContextBudget(max_chars=24_000, max_tokens=6_000)


@dataclass(frozen=True)
class ContextProfile:
    name: str
    budget: ContextBudget
    keep_recent_results: int = 2


CODER_PROFILE = ContextProfile(name="coder", budget=DEFAULT_BUDGET, keep_recent_results=2)
REVIEWER_PROFILE = ContextProfile(
    name="reviewer",
    budget=ContextBudget(max_chars=16_000, max_tokens=4_000),
    keep_recent_results=3,
)
