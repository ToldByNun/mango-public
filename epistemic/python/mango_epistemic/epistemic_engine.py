from __future__ import annotations

from typing import Any, Callable

from mango_epistemic.install_deps import ensure_packages, missing_import_roots
from mango_epistemic.parse import (
    evidence_from_tool_outputs,
    parse_epistemic_result,
    usable_api_brief,
    usable_api_signature,
)
from mango_epistemic.research_tools import format_usage_card, has_usage_hint, package_source_lookup
from mango_epistemic.sub_agent import ApiSubAgent
from mango_epistemic.targets import lookup_targets
from mango_epistemic.types import EpistemicResult
from mango_tools.tool_registry import ToolRegistry


class EpistemicEngine:
    """Spawns isolated sub-agents that share the main ModelRunner but not its context."""

    def __init__(
        self,
        model_runner: Any,
        *,
        web_backend: Callable[[str], Any] | None = None,
        max_iterations: int = 8,
        auto_install: bool = True,
    ) -> None:
        self._model_runner = model_runner
        self._web_backend = web_backend
        self._max_iterations = max_iterations
        self._auto_install = auto_install
        self.last_subagent_steps = 0
        self.last_subagent_prompt_chars = 0
        self.last_subagent_history_chars = 0
        self.total_asks = 0
        self.total_subagent_steps = 0
        self.last_result: EpistemicResult | None = None
        self.last_install: dict[str, Any] | None = None
        self.on_event: Callable[[dict[str, Any]], None] | None = None

    def ask_epistemic(
        self,
        question: str,
        *,
        libraries: list[str] | None = None,
        deadline: float | None = None,
    ) -> EpistemicResult:
        blob = question
        extra = " ".join(str(item) for item in (libraries or []) if str(item).strip())
        if extra:
            blob = f"{question}\n{extra}"
        targets = lookup_targets(blob)
        cards = [package_source_lookup(package, symbol) for package, symbol in targets]
        install_info = self._maybe_install_missing(cards, libraries or [])
        if install_info and install_info.get("installed"):
            cards = [package_source_lookup(package, symbol) for package, symbol in targets]
        self.last_install = install_info
        # Known stdlib cards are enough. Skipping the nested generate keeps the
        # main KV cache intact — a second complete() would llama.reset() it.
        skip_model = bool(targets) and all(
            has_usage_hint(package, symbol) and card.get("exists") is not False
            for (package, symbol), card in zip(targets, cards)
        )
        final_answer = ""
        if skip_model:
            final_answer = _usage_cards(cards)
            self.last_subagent_steps = 0
            self.last_subagent_prompt_chars = 0
            self.last_subagent_history_chars = 0
        else:
            sub = ApiSubAgent(
                self._model_runner,
                web_backend=self._web_backend,
                max_iterations=min(self._max_iterations, 2),
                on_event=None,
            )
            run = sub.run(question, cards=cards, deadline=deadline)
            self.last_subagent_steps = getattr(run, "iterations", 0)
            self.last_subagent_prompt_chars = sum(
                len(getattr(step, "prompt", "") or "") for step in getattr(run, "steps", []) or []
            )
            self.last_subagent_history_chars = _history_chars(getattr(run, "steps", []) or [])
            final_answer = getattr(run, "final_answer", "") or ""
        self.total_asks += 1
        self.total_subagent_steps += self.last_subagent_steps

        outputs = list(cards)
        extra = evidence_from_tool_outputs(outputs)
        result = parse_epistemic_result(question, final_answer, extra_evidence=extra)
        _fill_from_tool_outputs(result, outputs)
        if _looks_like_intent(result.details):
            result.details = None
        if not usable_api_brief(result.details):
            card = _usage_cards(outputs)
            if card:
                result.details = card
        if not result.details and result.signature and usable_api_signature(result.signature):
            result.details = result.signature
        if result.exists is None and extra:
            result.exists = True
        result.looked_up = [f"{pkg}.{sym}" if sym else pkg for pkg, sym in targets]
        self.last_result = result
        return result

    def _maybe_install_missing(
        self,
        cards: list[dict[str, Any]],
        libraries: list[str],
    ) -> dict[str, Any] | None:
        if not self._auto_install:
            return None
        roots = missing_import_roots(cards)
        for lib in libraries:
            root = str(lib or "").split(".", 1)[0].strip()
            if root and root not in roots:
                # Declared third-party that still isn't importable.
                from mango_epistemic.install_deps import can_import, resolve_pip_name

                if resolve_pip_name(root) and not can_import(root):
                    roots.append(root)
        if not roots:
            return None
        info = ensure_packages(roots)
        if self.on_event is not None and info.get("command"):
            try:
                self.on_event({"type": "install", "payload": info})
            except Exception:
                pass
        return info


def ask_epistemic(question: str, *, model_runner: Any, web_backend: Callable[[str], Any] | None = None) -> EpistemicResult:
    return EpistemicEngine(model_runner, web_backend=web_backend).ask_epistemic(question)


def register_ask_epistemic(
    registry: ToolRegistry,
    model_runner: Any,
    *,
    web_backend: Callable[[str], Any] | None = None,
    engine: EpistemicEngine | None = None,
    max_iterations: int = 8,
    get_deadline: Callable[[], float | None] | None = None,
) -> EpistemicEngine:
    engine = engine or EpistemicEngine(
        model_runner,
        web_backend=web_backend,
        max_iterations=max_iterations,
    )

    def _ask(question: str, _context: dict[str, Any] | None = None) -> dict[str, Any]:
        libs = []
        if isinstance(_context, dict):
            raw = _context.get("declared_libraries") or []
            if isinstance(raw, list):
                libs = [str(item) for item in raw if str(item).strip()]
        deadline = get_deadline() if get_deadline else None
        result = engine.ask_epistemic(question, libraries=libs, deadline=deadline)
        data = result.to_compact_dict()
        if result.looked_up:
            data["looked_up"] = list(result.looked_up)
        install = engine.last_install
        if isinstance(install, dict) and install.get("command"):
            data["install_command"] = install.get("command")
            data["installed"] = list(install.get("installed") or [])
            data["failed"] = list(install.get("failed") or [])
            data["install_ok"] = bool(install.get("ok"))
            data["install_stdout"] = str(install.get("stdout") or "")
            data["install_stderr"] = str(install.get("stderr") or "")
            # Only claim success when imports actually work after pip.
            if install.get("ok") and install.get("installed"):
                note = "Auto-installed: " + ", ".join(str(x) for x in install["installed"])
                details = str(data.get("details") or "").strip()
                data["details"] = f"{note}\n\n{details}".strip() if details else note
            elif install.get("failed") or not install.get("ok"):
                failed = install.get("failed") or []
                note = "Install failed for: " + ", ".join(str(x) for x in failed) if failed else "Install failed"
                details = str(data.get("details") or "").strip()
                data["details"] = f"{note}\n\n{details}".strip() if details else note
                data["exists"] = False
        useful = usable_api_brief(data.get("details")) or usable_api_signature(data.get("signature"))
        err_blob = f"{data.get('details') or ''} {data.get('error') or ''}".lower()
        import_miss = data.get("exists") is False and (
            "import failed" in err_blob
            or "no module named" in err_blob
            or "install failed" in err_blob
        )
        if import_miss:
            raise ValueError(
                "Package still missing after install attempt. "
                "Install failed or wrong PyPI name. "
                f"Tried: {data.get('install_command') or 'pip install <pkg>'}."
            )
        if not useful and data.get("exists") is not False:
            raise ValueError(
                "API research returned no usage brief. "
                "Call package_source_lookup with package AND symbol "
                "(e.g. package=collections, symbol=deque)."
            )
        return data

    if not registry.has("ask_epistemic"):
        registry.register(
            "ask_epistemic",
            _ask,
            description=(
                "Load API source for the named libraries and return a targeted usage brief. "
                "Nested lookups stay inside this tool; they are not extra chat turns."
            ),
            parameters={
                "question": {
                    "type": "string",
                    "description": "Libraries/symbols to analyze and what the coder will do with them",
                }
            },
            required=["question"],
        )
    return engine


def _tool_outputs(steps: list[Any]) -> list[Any]:
    outputs: list[Any] = []
    for step in steps:
        for result in getattr(step, "tool_results", None) or []:
            output = getattr(result, "output", None)
            if output is not None:
                outputs.append(output)
    return outputs


def _history_chars(steps: list[Any]) -> int:
    total = 0
    for step in steps:
        total += len(getattr(step, "prompt", "") or "")
        total += len(getattr(step, "model_output", "") or "")
        for result in getattr(step, "tool_results", None) or []:
            output = getattr(result, "output", None)
            if output is None:
                continue
            total += len(str(output))
    return total


def _fill_from_tool_outputs(result: EpistemicResult, outputs: list[Any]) -> None:
    signatures: list[str] = []
    exists: bool | None = None
    import_miss = False
    for output in outputs:
        if not isinstance(output, dict):
            continue
        err = str(output.get("error") or output.get("usage_card") or "").lower()
        if output.get("exists") is False and (
            "import failed" in err or "no module named" in err
        ):
            import_miss = True
            exists = False
        elif output.get("exists") is False:
            if exists is None:
                exists = False
        elif output.get("exists") is True or output.get("status") == "ok":
            if not import_miss:
                exists = True
        members = output.get("members")
        if isinstance(members, list) and members:
            question = (result.question or "").lower()
            picked: list[Any] = []
            for row in members:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").lower()
                if name and name in question:
                    picked.append(row)
            if not picked:
                picked = [row for row in members if isinstance(row, dict)][:4]
            for row in picked[:4]:
                sig = str(row.get("signature") or "").strip()
                if usable_api_signature(sig):
                    signatures.append(sig[:160])
        signature = str(output.get("signature") or "").strip()
        if usable_api_signature(signature) and signature.count(" | ") < 3:
            signatures.append(signature[:200])
    if signatures and (result.signature is None or not usable_api_signature(result.signature)):
        result.signature = " | ".join(dict.fromkeys(signatures))[:400]
    # Import failures always win over hallucinated free-text exists=True.
    if import_miss:
        result.exists = False
    elif result.exists is None and exists is not None:
        result.exists = exists


def _usage_cards(outputs: list[Any]) -> str:
    cards: list[str] = []
    seen: set[str] = set()
    for output in outputs:
        if not isinstance(output, dict):
            continue
        card = str(output.get("usage_card") or "").strip() or format_usage_card(output)
        if not card:
            continue
        key = card[:80]
        if key in seen:
            continue
        seen.add(key)
        cards.append(card)
    return "\n\n".join(cards)[:2_200]


def _looks_like_intent(text: str | None) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(
        token in low
        for token in (
            "i will ",
            "i'll ",
            "let me ",
            "using the doc_lookup",
            "using the tool",
            "next step is to research",
        )
    )
