from __future__ import annotations

from dataclasses import dataclass, field

from mango_cot.types import ReasoningNeed


@dataclass
class ThoughtTrace:
    """Lightweight log of reasoning cycles (not injected into the action prompt)."""

    entries: list[dict] = field(default_factory=list)

    def add(
        self,
        *,
        need: ReasoningNeed,
        prompt: str = "",
        raw: str = "",
        summary: str = "",
        cycle: int | None = None,
    ) -> None:
        self.entries.append(
            {
                "need": need.value if isinstance(need, ReasoningNeed) else str(need),
                "prompt_chars": len(prompt),
                "raw_chars": len(raw),
                "summary": summary.strip(),
                "cycle": cycle,
            }
        )
