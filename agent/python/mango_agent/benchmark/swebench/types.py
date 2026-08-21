"""Shared SWE-bench datatypes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SweBenchOutcome:
    instance_id: str
    repo: str
    success: bool
    resolved: bool | None
    model_patch: str
    patch_nonempty: bool
    stop_reason: str
    iterations: int
    elapsed_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tokens_estimated: bool
    model_complete_calls: int
    epistemic_calls: int
    verification_runs: int
    verification_failures: int
    reasoning_cycles: int = 0
    error: str | None = None
    harness_report: dict[str, Any] | None = None
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
