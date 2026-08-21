"""Thinking-level presets for GUI CoT + verify-first scaling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ThinkingLevel = Literal["off", "think", "deep", "max"]

_VALID = frozenset({"off", "think", "deep", "max"})


@dataclass(frozen=True)
class ThinkingPreset:
    level: ThinkingLevel
    chain_steps: int
    max_reasoning_cycles: int
    verify_strength: int  # 0=off, 1=soft, 2=deep, 3=max
    thought_max_tokens: int
    cot_short: int
    cot_extended: int
    thought_max_sentences: int
    thought_max_chars: int
    summary_max_tokens: int


_PRESETS: dict[str, ThinkingPreset] = {
    "off": ThinkingPreset("off", 0, 0, 0, 128, 128, 192, 2, 280, 280),
    "think": ThinkingPreset("think", 2, 3, 1, 256, 192, 256, 6, 800, 280),
    "deep": ThinkingPreset("deep", 4, 6, 2, 384, 256, 384, 10, 1400, 420),
    "max": ThinkingPreset("max", 6, 10, 3, 512, 384, 512, 10, 1400, 560),
}


def normalize_thinking_level(raw: str | None) -> ThinkingLevel:
    value = str(raw or "off").strip().lower()
    if value in _VALID:
        return value  # type: ignore[return-value]
    return "off"


def thinking_preset(raw: str | None) -> ThinkingPreset:
    return _PRESETS[normalize_thinking_level(raw)]


def verify_hint_for(strength: int) -> str:
    if strength <= 0:
        return ""
    if strength == 1:
        return (
            "Soft verify-first: inspect before edit; run/observe after changes when possible."
        )
    if strength == 2:
        return (
            "Strong verify-first: inspect → implement → run → observe → verify before finishing. "
            "Writing code is not completion."
        )
    return (
        "Strict verify-first: Understand → Inspect → Implement → Run → Observe → Verify → Fix → "
        "Verify again. Never finish on generation alone; re-verify after every fix."
    )
