from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryFact:
    """One durable, structured fact — not a chat turn."""

    kind: str
    key: str
    text: str
    iteration: int = 0


@dataclass
class DeterministicMemory:
    """Session memory the worker model sees instead of raw history."""

    facts: list[MemoryFact] = field(default_factory=list)
    max_facts: int = 20
    max_file_slices: int = 6

    def is_empty(self) -> bool:
        return not self.facts

    def upsert(self, kind: str, key: str, text: str, iteration: int = 0) -> None:
        token = f"{kind}:{key}"
        compact = (text or "").strip()
        if not compact:
            return
        self.facts = [fact for fact in self.facts if f"{fact.kind}:{fact.key}" != token]
        self.facts.append(MemoryFact(kind=kind, key=key, text=compact, iteration=iteration))
        overflow = len(self.facts) - self.max_facts
        if overflow > 0:
            self.facts = self.facts[overflow:]

    def render(self, *, max_chars: int = 1_600) -> str:
        if not self.facts:
            return ""
        others = [fact for fact in self.facts if fact.kind != "file"]
        files = [fact for fact in self.facts if fact.kind == "file"]
        blocks: list[str] = []
        for fact in others[-8:]:
            blocks.append(f"- {fact.kind} {fact.key}: {_one_line(fact.text, 140)}")
        for fact in files[-self.max_file_slices :]:
            label = fact.key.replace("\\", "/").rsplit("/", 1)[-1]
            blocks.append(f"### {label}\n{fact.text}")
        text = "\n".join(blocks).strip()
        if len(text) <= max_chars:
            return text
        while len(blocks) > 1 and len("\n".join(blocks)) > max_chars:
            blocks.pop(0)
        text = "\n".join(blocks).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 16].rstrip() + "\n...[memory]"


def _one_line(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
