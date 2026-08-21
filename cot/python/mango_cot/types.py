from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReasoningNeed(str, Enum):
    NONE = "none"
    SHORT = "short"
    EXTENDED = "extended"


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
