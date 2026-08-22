"""Workspace research sub-agent: locate → scan → deep Markdown docs for parent modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mango_tools import ToolRegistry, create_default_registry

_CODEBASE_READONLY = frozenset(
    {
        "list_dir",
        "glob_files",
        "read_file",
        "search_code",
        "codebase_lookup",
    }
)

_ALWAYS_DISABLE = frozenset(
    {
        "write_file",
        "edit_file",
        "edit_symbol",
        "rename_symbol",
        "delete_file",
        "run_tests",
        "run_terminal_command",
        "measure",
        "declare_apis",
        "ask_epistemic",
        "research_codebase",
    }
)


def register_research_codebase(
    registry: ToolRegistry,
    model_runner: Any,
    *,
    workspace: str | Path | None = None,
    get_workspace: Callable[[], str | Path | None] | None = None,
    get_deadline: Callable[[], float | None] | None = None,
    max_iterations: int = 10,
) -> None:
    """Register `research_codebase` — isolated read-only research for Ask/Plan/Agent/…"""

    def _research(question: str, _context: dict[str, Any] | None = None) -> dict[str, Any]:
        topic = (question or "").strip()
        if not topic:
            raise ValueError("research_codebase requires a non-empty question/topic")
        root: str | Path | None = None
        if get_workspace is not None:
            root = get_workspace()
        if root is None:
            root = workspace
        if root is None and isinstance(_context, dict):
            root = _context.get("workspace") or _context.get("cwd")
        if not root:
            raise ValueError("research_codebase needs a workspace path")
        deadline = get_deadline() if get_deadline else None
        docs = run_codebase_research(
            model_runner,
            topic,
            workspace=root,
            max_iterations=max_iterations,
            deadline=deadline,
        )
        if not (docs or "").strip():
            raise ValueError(
                "research_codebase returned empty documentation. "
                "Narrow the topic or ensure the workspace has readable sources."
            )
        return {
            "topic": topic,
            "details": docs.strip(),
            "exists": True,
        }

    if not registry.has("research_codebase"):
        registry.register(
            "research_codebase",
            _research,
            description=(
                "Research local workspace files for a topic: locate relevant paths, read them, "
                "and return in-depth Markdown docs (signatures, behavior, usage templates, deps). "
                "Use for Ask/Plan/Agent/Refactor/Debug codebase understanding. "
                "For third-party library APIs use ask_epistemic instead."
            ),
            parameters={
                "question": {
                    "type": "string",
                    "description": "Research topic or question about the local codebase",
                }
            },
            required=["question"],
        )


def run_codebase_research(
    model_runner: Any,
    question: str,
    *,
    workspace: str | Path,
    max_iterations: int = 10,
    deadline: float | None = None,
) -> str:
    """Spawn a read-only mini-agent and return its final Markdown documentation."""
    from mango_agent.agent import Agent
    from mango_agent.agent_context import AgentLimits
    from mango_agent.prompt import load_system_prompt

    root = Path(workspace).expanduser().resolve()
    registry = create_default_registry()
    disabled = set(_ALWAYS_DISABLE)
    for name in registry.list_tools():
        if name not in _CODEBASE_READONLY:
            disabled.add(name)

    sub = Agent(
        model_runner,
        tool_registry=registry,
        system_prompt=load_system_prompt("epistemic_codebase"),
        limits=AgentLimits(
            max_iterations=max(4, min(int(max_iterations), 12)),
            max_runtime_seconds=180,
            max_prompt_chars=20_000,
            max_reasoning_cycles=0,
            max_epistemic_iterations=0,
        ),
        codeintel_root=root,
        verification_root=root,
        require_tools=True,
        use_tool_grammar=True,
        thought_max_tokens=128,
        enable_declare_apis=False,
        task_wants_tests=False,
        plan_apis_first=False,
        plan_mode=True,
        disabled_tools=frozenset(disabled),
        thinking_level="off",
        agent_mode="epistemic_codebase",
        on_event=None,
    )
    result = sub.run(
        f"Research question:\n{question.strip()}\n\n"
        "Follow the epistemic codebase protocol. Finish with the Markdown documentation only.",
        deadline=deadline,
    )
    return str(getattr(result, "final_answer", "") or "").strip()
