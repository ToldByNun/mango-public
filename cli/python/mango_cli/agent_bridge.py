from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mango_agent import AgentLimits
from mango_agent.orchestrator import Orchestrator
from mango_agent.prompt import load_system_prompt
from mango_agent.serve import resolve_run_workspace
from mango_agent.thinking import thinking_preset
from mango_agent.types import AgentResult
from mango_runtime import ModelRunner


class AgentBridge:
    """Same Orchestrator stack as the Electron sidecar, in-process for the TUI."""

    def __init__(
        self,
        *,
        config_path: str | Path,
        workspace: str | Path,
        session_id: str = "cli",
    ) -> None:
        self._config_path = Path(config_path).expanduser().resolve()
        self._workspace = resolve_run_workspace(str(workspace), session_id)
        self._runner: ModelRunner | None = None
        self._orchestrator: Orchestrator | None = None
        self._cancel = threading.Event()
        self._event_handler: Callable[[dict[str, Any]], None] | None = None

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def model_path(self) -> str:
        if self._runner is None:
            return ""
        config = getattr(self._runner, "config", None)
        model = getattr(config, "model", None)
        return str(getattr(model, "path", "") or "")

    def load(self) -> None:
        if self._runner is not None:
            return
        runner = ModelRunner(str(self._config_path))
        runner.load()
        self._runner = runner

    def unload(self) -> None:
        if self._runner is not None:
            self._runner.unload()
        self._runner = None
        self._orchestrator = None

    def cancel(self) -> None:
        self._cancel.set()
        orch = self._orchestrator
        if orch is not None:
            orch.agent.cancel()

    def attach_event_handler(self, handler: Callable[[dict[str, Any]], None] | None) -> None:
        self._event_handler = handler
        if self._orchestrator is not None:
            self._orchestrator.agent._on_event = handler  # noqa: SLF001

    def run(self, goal: str, *, mode: str = "") -> AgentResult:
        self.load()
        assert self._runner is not None
        self._cancel.clear()
        orch = self._build_orchestrator(mode.strip().lower())
        self._orchestrator = orch
        if self._event_handler is not None:
            orch.agent._on_event = self._event_handler  # noqa: SLF001
        return orch.run(goal)

    def _build_orchestrator(self, mode: str) -> Orchestrator:
        assert self._runner is not None
        preset = thinking_preset("off")
        thought = preset.thought_max_tokens
        ws = str(self._workspace)
        base = {
            "max_tokens": 4096,
            "on_event": self._event_handler,
            "thought_max_tokens": thought,
            "tool_max_tokens": 3072,
            "thinking_level": preset.level,
        }
        if mode == "plan":
            return Orchestrator(
                self._runner,
                workspace=ws,
                limits=AgentLimits(
                    max_iterations=12,
                    max_runtime_seconds=600,
                    max_prompt_chars=24_000,
                    max_reasoning_cycles=preset.max_reasoning_cycles,
                    max_epistemic_iterations=8,
                ),
                system_prompt=load_system_prompt("plan"),
                require_tools=True,
                plan_mode=True,
                plan_apis_first=False,
                task_wants_tests=False,
                disabled_tools=frozenset({"declare_apis"}),
                agent_mode="plan",
                **base,
            )
        if mode == "ask":
            return Orchestrator(
                self._runner,
                workspace=ws,
                limits=AgentLimits(
                    max_iterations=14,
                    max_runtime_seconds=600,
                    max_prompt_chars=24_000,
                    max_reasoning_cycles=preset.max_reasoning_cycles,
                    max_epistemic_iterations=8,
                ),
                system_prompt=load_system_prompt("ask"),
                require_tools=True,
                plan_mode=True,
                plan_apis_first=False,
                task_wants_tests=False,
                disabled_tools=frozenset(
                    {
                        "declare_apis",
                        "codebase_lookup",
                        "ask_epistemic",
                        "research_codebase",
                        "package_source_lookup",
                        "doc_lookup",
                        "web_research",
                    }
                ),
                agent_mode="ask",
                **base,
            )
        if mode == "refactor":
            return Orchestrator(
                self._runner,
                workspace=ws,
                limits=AgentLimits(
                    max_iterations=16,
                    max_runtime_seconds=600,
                    max_prompt_chars=24_000,
                    max_reasoning_cycles=preset.max_reasoning_cycles,
                    max_epistemic_iterations=6,
                ),
                system_prompt=load_system_prompt("refactor"),
                require_tools=True,
                plan_apis_first=False,
                task_wants_tests=False,
                disabled_tools=frozenset(
                    {"write_file", "delete_file", "run_terminal_command", "measure"}
                ),
                agent_mode="refactor",
                **base,
            )
        if mode == "debug":
            return Orchestrator(
                self._runner,
                workspace=ws,
                limits=AgentLimits(
                    max_iterations=20,
                    max_runtime_seconds=900,
                    max_prompt_chars=24_000,
                    max_reasoning_cycles=preset.max_reasoning_cycles,
                    max_epistemic_iterations=8,
                ),
                system_prompt=load_system_prompt("debug"),
                require_tools=True,
                plan_apis_first=True,
                task_wants_tests=True,
                agent_mode="debug",
                **base,
            )
        return Orchestrator(
            self._runner,
            workspace=ws,
            limits=AgentLimits(
                max_iterations=20,
                max_runtime_seconds=900,
                max_prompt_chars=24_000,
                max_reasoning_cycles=preset.max_reasoning_cycles,
                max_epistemic_iterations=8,
            ),
            require_tools=True,
            plan_apis_first=True,
            # Detect from the goal — forcing True made Discord creates burn the
            # deadline writing hollow test_impl.py instead of finishing the bot.
            task_wants_tests=None,
            tool_max_tokens=3072,
            thought_max_tokens=thought,
            thinking_level=preset.level,
            max_tokens=4096,
            on_event=self._event_handler,
            agent_mode="agent",
        )
