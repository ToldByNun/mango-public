from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from mango_tools.types import ToolCall, ToolResult


class StopReason(str, Enum):
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"
    VERIFICATION_FAILED = "verification_failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class AgentLimits:
    """Budgets applied across the main loop and nested engines."""

    max_iterations: int = 10
    max_runtime_seconds: float = 300.0
    max_reasoning_cycles: int = 20
    max_fix_attempts: int = 5
    max_epistemic_iterations: int = 6
    max_prompt_chars: int = 24_000


@dataclass(frozen=True)
class LoopMetrics:
    iterations: int = 0
    final_prompt_chars: int = 0
    tool_call_count: int = 0
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    reasoning_cycles: int = 0
    epistemic_calls: int = 0
    epistemic_subagent_iterations: int = 0
    verification_runs: int = 0
    verification_failures: int = 0
    elapsed_seconds: float = 0.0
    edit_fail_count: int = 0
    write_fail_count: int = 0
    edit_attempts: int = 0
    write_attempts: int = 0
    edit_fail_rate: float = 0.0
    identical_tool_repeat_max: int = 0
    stall_triggered: bool = False
    stall_stopped: bool = False
    grammar_tool_count: int = 0
    grammar_missing_core_tools: list[str] = field(default_factory=list)
    grammar_filtered_tools: list[str] = field(default_factory=list)
    ttft_ms: float = 0.0
    total_prefill_s: float = 0.0
    total_decode_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    plan_gate_turns: int = 0
    prompt_variant: str = "v1"
    tool_filter_mode: str = "complete"
    tool_profile: str = "standard"
    reset_cache_used: int = 0

    def format_log(self, scenario: str = "", *, stop_reason: str = "") -> str:
        title = scenario.strip() or "run"
        names = ", ".join(f"{name}={count}" for name, count in sorted(self.tool_calls_by_name.items())) or "(none)"
        lines = [
            f"[Mango E2E] {title}",
            f"  stop={stop_reason or '-'} iterations={self.iterations} elapsed_s={self.elapsed_seconds:.4f}",
            f"  final_prompt_chars={self.final_prompt_chars}",
            f"  tool_calls={self.tool_call_count} [{names}]",
            f"  reasoning_cycles={self.reasoning_cycles}",
            f"  epistemic_calls={self.epistemic_calls} epistemic_subagent_iterations={self.epistemic_subagent_iterations}",
            f"  verification_runs={self.verification_runs} verification_failures={self.verification_failures}",
            f"  edit_fail_rate={self.edit_fail_rate} stall_stopped={self.stall_stopped}",
            f"  grammar_missing_core={self.grammar_missing_core_tools or '(none)'}",
            f"  ttft_ms={self.ttft_ms} prefill_s={self.total_prefill_s} decode_s={self.total_decode_s}",
        ]
        return "\n".join(lines)


def log_loop_metrics(result: AgentResult, scenario: str = "") -> str:
    text = result.metrics.format_log(scenario, stop_reason=result.stop_reason.value)
    print(text, flush=True)
    return text


@dataclass(frozen=True)
class AgentStep:
    iteration: int
    prompt: str
    model_output: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    reasoning_need: str | None = None
    reasoning_summary: str | None = None


@dataclass(frozen=True)
class AgentResult:
    final_answer: str
    steps: list[AgentStep]
    iterations: int
    stop_reason: StopReason
    error: str | None = None
    verification_attempts: int = 0
    verification_report: str | None = None
    metrics: LoopMetrics = field(default_factory=LoopMetrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "iterations": self.iterations,
            "stop_reason": self.stop_reason.value,
            "error": self.error,
            "verification_attempts": self.verification_attempts,
            "verification_report": self.verification_report,
            "metrics": {
                "iterations": self.metrics.iterations,
                "final_prompt_chars": self.metrics.final_prompt_chars,
                "tool_call_count": self.metrics.tool_call_count,
                "tool_calls_by_name": self.metrics.tool_calls_by_name,
                "reasoning_cycles": self.metrics.reasoning_cycles,
                "epistemic_calls": self.metrics.epistemic_calls,
                "epistemic_subagent_iterations": self.metrics.epistemic_subagent_iterations,
                "verification_runs": self.metrics.verification_runs,
                "verification_failures": self.metrics.verification_failures,
                "elapsed_seconds": self.metrics.elapsed_seconds,
                "edit_fail_count": self.metrics.edit_fail_count,
                "write_fail_count": self.metrics.write_fail_count,
                "edit_attempts": self.metrics.edit_attempts,
                "write_attempts": self.metrics.write_attempts,
                "edit_fail_rate": self.metrics.edit_fail_rate,
                "identical_tool_repeat_max": self.metrics.identical_tool_repeat_max,
                "stall_triggered": self.metrics.stall_triggered,
                "stall_stopped": self.metrics.stall_stopped,
                "grammar_tool_count": self.metrics.grammar_tool_count,
                "grammar_missing_core_tools": self.metrics.grammar_missing_core_tools,
                "grammar_filtered_tools": self.metrics.grammar_filtered_tools,
                "ttft_ms": self.metrics.ttft_ms,
                "total_prefill_s": self.metrics.total_prefill_s,
                "total_decode_s": self.metrics.total_decode_s,
                "prompt_tokens": self.metrics.prompt_tokens,
                "completion_tokens": self.metrics.completion_tokens,
                "plan_gate_turns": self.metrics.plan_gate_turns,
                "prompt_variant": self.metrics.prompt_variant,
                "tool_filter_mode": self.metrics.tool_filter_mode,
                "tool_profile": self.metrics.tool_profile,
                "reset_cache_used": self.metrics.reset_cache_used,
            },
            "steps": [
                {
                    "iteration": step.iteration,
                    "model_output": step.model_output,
                    "tool_calls": [call.name for call in step.tool_calls],
                    "tool_results": [result.to_dict() for result in step.tool_results],
                    "reasoning_need": step.reasoning_need,
                    "reasoning_summary": step.reasoning_summary,
                }
                for step in self.steps
            ],
        }


class ModelRunnerProtocol(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        reset_cache: bool = True,
        grammar: Any | None = None,
        grammar_trigger: str | None = None,
        thought_max_tokens: int | None = None,
        tool_max_tokens: int | None = None,
        force_grammar: bool = False,
        on_token: Any = None,
        on_phase: Any = None,
        should_cancel: Any = None,
    ) -> Any: ...
