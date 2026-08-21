"""Mango Agent — full main loop across all modules."""

from mango_agent.agent import Agent, create_agent
from mango_agent.agent_context import AgentLimits, WorkspaceConfig
from mango_agent.orchestrator import Orchestrator, create_orchestrator
from mango_agent.prompt import DEFAULT_SYSTEM_PROMPT, load_system_prompt, render_system_prompt
from mango_agent.types import AgentResult, AgentStep, LoopMetrics, StopReason, log_loop_metrics

__all__ = [
    "Agent",
    "AgentLimits",
    "AgentResult",
    "AgentStep",
    "DEFAULT_SYSTEM_PROMPT",
    "LoopMetrics",
    "Orchestrator",
    "StopReason",
    "WorkspaceConfig",
    "create_agent",
    "create_orchestrator",
    "load_system_prompt",
    "log_loop_metrics",
    "render_system_prompt",
]
