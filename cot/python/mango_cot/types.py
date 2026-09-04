from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict


class ReasoningNeed(str, Enum):
    NONE = "none"
    SHORT = "short"
    EXTENDED = "extended"


class CotStepPayload(TypedDict, total=False):
    """GBNF/JSON reasoning step shape at the CoT engine edge."""

    known_facts: list[str]
    decisions: list[str]
    assumptions: list[str]
    failed_attempts: list[str]
    open_questions: list[str]
    next_action: str
    summary: str
    verify_plan: list[str]
    step: str


class CotChainStepEvent(TypedDict):
    """Callback payload when a chain step completes (service edge)."""

    index: int
    text: str


def as_cot_step_payload(raw: dict[str, Any]) -> CotStepPayload:
    """Normalize a parsed CoT JSON object into the public step contract."""
    if not isinstance(raw, dict):
        return {}
    out: CotStepPayload = {}
    for key in (
        "known_facts",
        "decisions",
        "assumptions",
        "failed_attempts",
        "open_questions",
        "verify_plan",
    ):
        value = raw.get(key)
        if isinstance(value, list):
            out[key] = [str(item) for item in value]  # type: ignore[literal-required]
    for key in ("next_action", "summary", "step"):
        value = raw.get(key)
        if value is not None:
            out[key] = str(value)  # type: ignore[literal-required]
    return out


@dataclass
class ReasoningState:
    goal: str
    known_facts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    failed_attempts: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_action: str = ""
    cycle_summaries: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.known_facts
            or self.decisions
            or self.assumptions
            or self.failed_attempts
            or self.open_questions
            or self.next_action.strip()
            or self.cycle_summaries
        )

    def append_unique(self, field_name: str, values: list[str], *, cap: int = 20) -> None:
        bucket: list[str] = getattr(self, field_name)
        for value in values:
            text = " ".join(value.split()).strip()
            if not text or text in bucket:
                continue
            bucket.append(text)
        setattr(self, field_name, bucket[-cap:])
