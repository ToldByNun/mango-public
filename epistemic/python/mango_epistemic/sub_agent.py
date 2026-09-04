from __future__ import annotations

from typing import Any

_GOAL = """Isolated API analysis. Empty chat — no coder context, no user files.

Question from the coder:
{question}

API source is already loaded. Do not call tools. Write a TARGETED usage brief for this question only.

{cards}

MUST:
- Exact import and real arguments for each callable the coder needs.
- One short snippet per API (how to use it for THIS question).
- Complexity / pitfalls (O(1) popleft, Lock() is a factory, monotonic vs time, …).
- Skip unused module members. No inspect junk like (/, *args, **kwargs). No JSON. No plan.
"""


class ApiSubAgent:
    """One isolated summarize turn. Lookups are done by the runner, not the model."""

    def __init__(
        self,
        model_runner: Any,
        *,
        web_backend: Any | None = None,
        max_iterations: int = 2,
        max_tokens: int | None = 768,
        max_prompt_chars: int = 16_000,
        on_event: Any | None = None,
        addon_system_prompt: str | None = None,
    ) -> None:
        self._model_runner = model_runner
        self._web_backend = web_backend
        self._max_iterations = max_iterations
        self._max_tokens = max_tokens
        self._max_prompt_chars = max_prompt_chars
        self._on_event = on_event
        self._addon_system_prompt = (addon_system_prompt or "").strip()
        self.last_run: Any = None

    def run(
        self,
        question: str,
        *,
        cards: list[dict[str, Any]] | None = None,
        deadline: float | None = None,
    ) -> Any:
        from mango_agent.agent import Agent
        from mango_agent.prompt import EPISTEMIC_SYSTEM_PROMPT
        from mango_tools.tool_registry import ToolRegistry

        card_text = _render_cards(cards or [])
        goal = _GOAL.replace("{question}", question.strip()).replace(
            "{cards}", card_text or "(no source loaded)"
        )
        system = EPISTEMIC_SYSTEM_PROMPT
        if self._addon_system_prompt:
            system = (
                f"{system}\n\n<continuation_system_prompt>\n"
                f"{self._addon_system_prompt}\n</continuation_system_prompt>"
            )
        sub = Agent(
            self._model_runner,
            tool_registry=ToolRegistry(),
            system_prompt=system,
            max_iterations=min(self._max_iterations, 2),
            max_tokens=self._max_tokens,
            max_prompt_chars=self._max_prompt_chars,
            require_tools=False,
            use_tool_grammar=False,
            max_reasoning_cycles=0,
            thought_max_tokens=192,
            enable_declare_apis=False,
            task_wants_tests=False,
            on_event=None,
        )
        self.last_run = sub.run(goal, deadline=deadline)
        return self.last_run


def _render_cards(cards: list[dict[str, Any]]) -> str:
    from mango_epistemic.research_tools import format_usage_card

    blocks: list[str] = []
    for card in cards:
        text = str(card.get("usage_card") or format_usage_card(card) or "").strip()
        if text:
            blocks.append(text)
    return "\n\n".join(blocks)
