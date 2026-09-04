"""Mango CoT — Chain-of-Thought engine (ReasoningState, separate from ContextState)."""

from mango_cot.classify import GoalTargets, classify_reasoning_need, extract_goal_targets
from mango_cot.compress import compress_reasoning_state, thought_for_ui
from mango_cot.cot_engine import REASONING_MARKER, CoTEngine, run_reasoning_cycle
from mango_cot.thought_trace import ThoughtTrace
from mango_cot.types import (
    CotStepPayload,
    ReasoningNeed,
    ReasoningState,
    as_cot_step_payload,
)

__all__ = [
    "REASONING_MARKER",
    "CoTEngine",
    "CotStepPayload",
    "GoalTargets",
    "ReasoningNeed",
    "ReasoningState",
    "ThoughtTrace",
    "as_cot_step_payload",
    "classify_reasoning_need",
    "compress_reasoning_state",
    "thought_for_ui",
    "extract_goal_targets",
    "run_reasoning_cycle",
]
