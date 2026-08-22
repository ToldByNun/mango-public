from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mango_context.memory import DeterministicMemory


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Good enough for window budgeting."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


@dataclass
class ContextBudget:
    max_chars: int = 24_000
    max_tokens: int | None = None
    max_stored_result_chars: int = 32_000
    max_actions: int = 40
    max_relevant_files: int = 40
    keep_recent_results: int = 2
    body_lines: int = 5
    memory_max_chars: int = 1_600

    @property
    def char_limit(self) -> int:
        if self.max_tokens is None:
            return self.max_chars
        return min(self.max_chars, self.max_tokens * 4)


@dataclass
class ActionRecord:
    iteration: int
    summary: str


@dataclass
class ToolResultEntry:
    iteration: int
    tool_name: str
    success: bool
    body: str
    original_chars: int = 0
    error: str | None = None

    def __post_init__(self) -> None:
        if self.original_chars == 0:
            self.original_chars = len(self.body)


@dataclass
class ToolSpec:
    name: str
    description: str


@dataclass
class ContextState:
    goal: str
    constraints: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    previous_actions: list[ActionRecord] = field(default_factory=list)
    tool_results: list[ToolResultEntry] = field(default_factory=list)
    system_prompt: str = ""
    tool_instruction: str = ""
    available_tools: list[ToolSpec] = field(default_factory=list)
    reasoning_summary: str = ""
    work_plan: str = ""
    impl_status: str = ""
    verification_feedback: str = ""
    verification_failed_tests: list[str] = field(default_factory=list)
    verification_impl_paths: list[str] = field(default_factory=list)
    verification_impl_symbols: list[str] = field(default_factory=list)
    verification_collection_error: bool = False
    verification_next_edit: str = ""
    verification_missing_symbol: str | None = None
    verification_missing_module: str | None = None
    verification_current_source: str = ""
    last_noop_snippet: str = ""
    allow_multi_edit: bool = False
    budget: ContextBudget = field(default_factory=ContextBudget)
    memory: DeterministicMemory = field(default_factory=DeterministicMemory)

    def add_constraint(self, constraint: str) -> None:
        text = constraint.strip()
        if text and text not in self.constraints:
            self.constraints.append(text)

    def note_file(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        if path in self.relevant_files:
            self.relevant_files.remove(path)
        self.relevant_files.append(path)
        overflow = len(self.relevant_files) - self.budget.max_relevant_files
        if overflow > 0:
            self.relevant_files = self.relevant_files[overflow:]

    def record_action(self, iteration: int, summary: str) -> None:
        self.previous_actions.append(ActionRecord(iteration=iteration, summary=summary.strip()))
        overflow = len(self.previous_actions) - self.budget.max_actions
        if overflow > 0:
            self.previous_actions = self.previous_actions[overflow:]

    def record_tool_result(
        self,
        iteration: int,
        tool_name: str,
        success: bool,
        body: str,
        *,
        error: str | None = None,
    ) -> None:
        cap = self.budget.max_stored_result_chars
        original = len(body)
        stored = body
        if original > cap:
            stored = body[:cap] + f"\n...[stored truncated {original - cap} chars]"
        self.tool_results.append(
            ToolResultEntry(
                iteration=iteration,
                tool_name=tool_name,
                success=success,
                body=stored,
                original_chars=original,
                error=error,
            )
        )
