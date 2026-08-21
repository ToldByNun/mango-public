"""Agent runtime — re-exports the full main loop."""

from mango_agent.agent import Agent, create_agent
from mango_agent.orchestrator import Orchestrator, create_orchestrator

AgentRuntime = Orchestrator

__all__ = ["Agent", "AgentRuntime", "Orchestrator", "create_agent", "create_orchestrator"]
