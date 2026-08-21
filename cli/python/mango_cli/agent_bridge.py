from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mango_agent.thinking import thinking_preset
from mango_agent.orchestrator import Orchestrator
from mango_agent.serve import resolve_run_workspace
from mango_agent.types import AgentResult
from mango_runtime import ModelRunner


class AgentBridge:
    """Run the same Orchestrator stack as the Electron sidecar, in-process."""

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

    @property
    def workspace(self) -> Path:
        return self._workspace

    def load(self) -> None:
        if self._runner is not None:
            return
        runner = ModelRunner(str(self._config_path))
        runner.load()
        self._runner = runner
        preset = thinking_preset("off")
        self._orchestrator = Orchestrator(
            runner,
            workspace=str(self._workspace),
            limits=AgentLimits(
                max_iterations=20,
                max_runtime_seconds=900,
                max_prompt_chars=24_000,
                max_reasoning_cycles=preset.max_reasoning_cycles,
                max_epistemic_iterations=8,
            ),
            max_tokens=4096,
            require_tools=True,
            plan_apis_first=True,
            task_wants_tests=True,
            thought_max_tokens=preset.thought_max_tokens,
            tool_max_tokens=2048,
            thinking_level=preset.level,
        )

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

    def run(
        self,
        goal: str,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentResult:
        if self._orchestrator is None:
            self.load()
        assert self._orchestrator is not None
        self._cancel.clear()
        return self._orchestrator.run(goal)

    def attach_event_handler(
        self,
        handler: Callable[[dict[str, Any]], None] | None,
    ) -> Orchestrator:
        if self._orchestrator is None:
            self.load()
        assert self._orchestrator is not None
        self._orchestrator.agent._on_event = handler  # noqa: SLF001 — CLI shares GUI hook
        return self._orchestrator
