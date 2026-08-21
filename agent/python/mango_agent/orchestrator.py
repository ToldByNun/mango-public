"""Full Mango main loop: context + CoT + tools + codeintel + epistemic + verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mango_agent.agent import Agent, create_agent
from mango_agent.agent_context import AgentLimits, WorkspaceConfig
from mango_agent.types import AgentResult, ModelRunnerProtocol


class Orchestrator:
    """Wires every module into one Agent and runs the main loop under shared limits."""

    def __init__(
        self,
        model_runner: ModelRunnerProtocol,
        *,
        workspace: str | Path,
        limits: AgentLimits | None = None,
        verification_config: Any | None = None,
        epistemic_web_backend: Any | None = None,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = 0.1,
        top_p: float | None = 0.95,
        use_tool_grammar: bool = True,
        thought_max_tokens: int | None = None,
        tool_max_tokens: int | None = None,
        on_event: Any | None = None,
        require_tools: bool = False,
        task_wants_tests: bool | None = None,
        plan_apis_first: bool = False,
        verbose: bool = False,
        disabled_tools: frozenset[str] | set[str] | None = None,
        thinking_level: str | None = None,
    ) -> None:
        self.workspace = WorkspaceConfig(root=Path(workspace))
        self.limits = limits or AgentLimits()
        self.agent = Agent(
            model_runner,
            limits=self.limits,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            epistemic_web_backend=epistemic_web_backend,
            codeintel_root=self.workspace.codeintel_root,
            verification_root=self.workspace.verification_root,
            verification_config=verification_config,
            use_tool_grammar=use_tool_grammar,
            thought_max_tokens=thought_max_tokens,
            tool_max_tokens=tool_max_tokens,
            on_event=on_event,
            require_tools=require_tools,
            task_wants_tests=task_wants_tests,
            plan_apis_first=plan_apis_first,
            verbose=verbose,
            disabled_tools=disabled_tools,
            thinking_level=thinking_level,
        )

    def run(self, task: str) -> AgentResult:
        return self.agent.run(task)


def create_orchestrator(
    workspace: str | Path,
    *,
    runtime_config: str | None = None,
    limits: AgentLimits | None = None,
    load_model: bool = True,
    **kwargs: Any,
) -> Orchestrator:
    from mango_runtime import ModelRunner

    runner = ModelRunner(runtime_config)
    if load_model:
        runner.load()
    return Orchestrator(runner, workspace=workspace, limits=limits, **kwargs)


__all__ = ["AgentLimits", "Orchestrator", "WorkspaceConfig", "create_agent", "create_orchestrator"]
