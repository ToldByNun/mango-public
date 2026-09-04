from __future__ import annotations

import json
from typing import Any, Callable, Protocol

from mango_cot.classify import classify_reasoning_need
from mango_cot.compress import compress_reasoning_state
from mango_cot.json_gbnf import REASONING_JSON_GBNF
from mango_cot.parse import parse_reasoning_payload
from mango_cot.prompt import render_system_prompt
from mango_cot.thought_trace import ThoughtTrace
from mango_cot.types import ReasoningNeed, ReasoningState

REASONING_MARKER = "[Mango reasoning cycle]"

SHORT_MAX_TOKENS = 192
EXTENDED_MAX_TOKENS = 384

# Under a JSON grammar the model sometimes copies the schema from the prompt
# instead of filling it in, which used to surface as "[summary] string | next=string".
_SCHEMA_PLACEHOLDERS = frozenset(
    {
        "string",
        "str",
        "strings",
        "text",
        "thought",
        "summary",
        "next_action",
        "verify_plan",
        "known_facts",
        "...",
        "…",
        "n/a",
        "none",
        "null",
        "todo",
        "tbd",
    }
)


class ModelRunnerLike(Protocol):
    def complete(self, prompt: str, **kwargs: Any) -> Any: ...


def run_reasoning_cycle(
    reasoning_state: ReasoningState,
    context_state: Any,
    model_runner: ModelRunnerLike,
    *,
    need: ReasoningNeed | str | None = None,
    prior_thought: str = "",
    short_max_tokens: int = SHORT_MAX_TOKENS,
    extended_max_tokens: int = EXTENDED_MAX_TOKENS,
) -> str:
    """Run a reasoning cycle. "none" returns the state unchanged (no model call)."""
    resolved = _resolve_need(need, reasoning_state, context_state)
    if resolved is ReasoningNeed.NONE:
        return ""

    _sync_failures_from_context(reasoning_state, context_state)
    prompt = _build_reasoning_prompt(
        reasoning_state,
        context_state,
        resolved,
        prior_thought=prior_thought,
    )
    completion = model_runner.complete(
        prompt,
        max_tokens=short_max_tokens if resolved is ReasoningNeed.SHORT else extended_max_tokens,
        temperature=0.1,
        top_p=0.95,
        reset_cache=False,
        grammar=REASONING_JSON_GBNF,
        force_grammar=True,
    )
    raw = str(getattr(completion, "text", completion) or "")
    payload = parse_reasoning_payload(raw)
    if resolved is ReasoningNeed.SHORT:
        _apply_short(reasoning_state, payload)
    else:
        _apply_extended(reasoning_state, payload)
    return raw


class CoTEngine:
    def __init__(
        self,
        goal: str,
        *,
        short_max_tokens: int = SHORT_MAX_TOKENS,
        extended_max_tokens: int = EXTENDED_MAX_TOKENS,
    ) -> None:
        self.state = ReasoningState(goal=goal.strip())
        self.trace = ThoughtTrace()
        self.last_need: ReasoningNeed = ReasoningNeed.NONE
        self._cycle_counter = 0
        self._short_max_tokens = short_max_tokens
        self._extended_max_tokens = extended_max_tokens

    def run_cycle(
        self,
        context_state: Any,
        model_runner: ModelRunnerLike,
        *,
        allow_model: bool = True,
    ) -> ReasoningState:
        self.last_need = classify_reasoning_need(
            self.state.goal,
            context_state,
            self.state,
        )
        if self.last_need is ReasoningNeed.NONE or not allow_model:
            self.trace.add(need=self.last_need, cycle=self._cycle_counter)
            return self.state
        prompt = _build_reasoning_prompt(
            self.state,
            context_state,
            self.last_need,
            prior_thought=_latest_cycle_summary(self.state),
        )
        raw = run_reasoning_cycle(
            self.state,
            context_state,
            model_runner,
            need=self.last_need,
            prior_thought=_latest_cycle_summary(self.state),
            short_max_tokens=self._short_max_tokens,
            extended_max_tokens=self._extended_max_tokens,
        )
        self._cycle_counter += 1
        summary = _cycle_summary(self.state)
        if summary:
            self.state.append_unique(
                "cycle_summaries",
                [summary],
                cap=8,
            )
        self.trace.add(
            need=self.last_need,
            prompt=prompt,
            raw=raw,
            summary=summary,
            cycle=self._cycle_counter,
        )
        return self.state

    def compressed_summary(self, *, max_chars: int = 720) -> str:
        return compress_reasoning_state(self.state, max_chars=max_chars)

    def run_chained(
        self,
        model_runner: ModelRunnerLike,
        *,
        steps: int,
        verify_level: str = "think",
        verify_hint: str = "",
        context_state: Any = None,
        max_tokens: int = 256,
        on_step: Callable[[int, str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        force_next_tools: list[str] | None = None,
    ) -> str:
        """Cumulative CoT chain: step N sees steps 1..N-1; final call summarizes for the main agent.

        Returns the final summary string only (never the raw step dump).
        Early-stops when steps paraphrase each other (SLM echo loops).
        """
        n = max(0, int(steps))
        if n <= 0:
            return ""

        step_texts: list[str] = []
        next_actions: list[str] = []
        snapshot = _context_snapshot(context_state) if context_state is not None else "(no context yet)"
        level = str(verify_level or "think")
        forced = [str(x).strip() for x in (force_next_tools or []) if str(x).strip()]
        echo_streak = 0

        for index in range(1, n + 1):
            if should_cancel is not None and should_cancel():
                break
            prior = _format_prior_steps(step_texts)
            step_hint = _chain_step_hint(
                base_hint=verify_hint or "",
                step_index=index,
                prior_texts=step_texts,
                prior_actions=next_actions,
                force_next_tools=forced,
            )
            prompt = render_system_prompt(
                "cot_chain_step",
                marker=REASONING_MARKER,
                step=str(index),
                steps=str(n),
                verify_level=level,
                goal=self.state.goal,
                prior_steps=prior,
                snapshot=snapshot,
                verify_hint=step_hint,
            )
            completion = model_runner.complete(
                prompt,
                max_tokens=max_tokens,
                temperature=0.1,
                top_p=0.95,
                reset_cache=False,
                grammar=REASONING_JSON_GBNF,
                force_grammar=True,
            )
            raw = str(getattr(completion, "text", completion) or "")
            payload = parse_reasoning_payload(raw)
            text = _chain_step_text(payload, raw)
            action = _as_text(payload.get("next_action"))
            # Exact or near-duplicate steps add nothing — abort the echo loop.
            fresh = bool(text) and text not in step_texts and not _near_duplicate(text, step_texts)
            action_fresh = bool(action) and action.lower() not in {a.lower() for a in next_actions}
            if fresh:
                step_texts.append(text)
                if action:
                    next_actions.append(action)
                echo_streak = 0
            else:
                echo_streak += 1
            self._cycle_counter += 1
            self.trace.add(
                need=ReasoningNeed.EXTENDED,
                prompt=prompt,
                raw=raw,
                summary=(text or raw)[:240],
                cycle=self._cycle_counter,
            )
            if on_step is not None and fresh:
                on_step(index, text)
            # Two echo steps in a row (or same next_action thrice) → stop burning tokens.
            if echo_streak >= 1 and index >= 2:
                break
            if not action_fresh and index >= 2 and len(next_actions) >= 2:
                if next_actions[-1].lower() == next_actions[-2].lower():
                    break

        if not step_texts:
            return ""

        if should_cancel is not None and should_cancel():
            return _one_line(step_texts[-1], 400)

        all_steps = _format_prior_steps(step_texts)
        summarize_hint = ""
        if forced:
            summarize_hint = (
                " next_action MUST be exactly one of: "
                + ", ".join(forced[:4])
                + ". Do NOT restate blockers."
            )
        summary_prompt = render_system_prompt(
            "cot_chain_summarize",
            marker=REASONING_MARKER,
            goal=self.state.goal,
            all_steps=all_steps,
            summarize_hint=summarize_hint,
        )
        completion = model_runner.complete(
            summary_prompt,
            max_tokens=max(192, max_tokens),
            temperature=0.1,
            top_p=0.95,
            reset_cache=False,
            grammar=REASONING_JSON_GBNF,
            force_grammar=True,
        )
        raw = str(getattr(completion, "text", completion) or "")
        payload = parse_reasoning_payload(raw)
        summary = _chain_summary_text(payload, step_texts)
        # If summarize also echoed a blocker without a tool, inject forced next.
        if forced and not _mentions_any_tool(summary, forced):
            summary = (
                f"{summary} | next={forced[0]}" if summary else f"next={forced[0]}"
            ).strip()
            self.state.next_action = forced[0]
        self._cycle_counter += 1
        self.trace.add(
            need=ReasoningNeed.EXTENDED,
            prompt=summary_prompt,
            raw=raw,
            summary=summary[:240],
            cycle=self._cycle_counter,
        )
        if summary:
            self.state.next_action = _as_text(payload.get("next_action")) or self.state.next_action
            if forced and not _mentions_any_tool(self.state.next_action, forced):
                self.state.next_action = forced[0]
            self.state.append_unique("cycle_summaries", [summary], cap=8)
            facts = _as_str_list(payload.get("verify_plan"))
            if facts:
                self.state.append_unique("decisions", facts, cap=15)
        return summary


def _format_prior_steps(steps: list[str]) -> str:
    if not steps:
        return "(none yet — this is step 1)"
    lines: list[str] = []
    for i, text in enumerate(steps, start=1):
        lines.append(f"[CoT{i}] {_one_line(text, 600)}")
    return "\n".join(lines)


def _tokenize(text: str) -> set[str]:
    return {tok for tok in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(tok) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _near_duplicate(text: str, prior: list[str], *, threshold: float = 0.72) -> bool:
    tokens = _tokenize(text)
    if len(tokens) < 6:
        return False
    for prev in prior:
        if _jaccard(tokens, _tokenize(prev)) >= threshold:
            return True
    return False


def _mentions_any_tool(text: str, tools: list[str]) -> bool:
    low = (text or "").lower()
    return any(t.lower() in low for t in tools)


def _chain_step_hint(
    *,
    base_hint: str,
    step_index: int,
    prior_texts: list[str],
    prior_actions: list[str],
    force_next_tools: list[str],
) -> str:
    parts: list[str] = []
    if base_hint.strip():
        parts.append(base_hint.strip())
    blob = " ".join(prior_texts).lower()
    if step_index == 1:
        parts.append(
            "Do NOT assume you already know APIs or that deps are installed. "
            "Name ONE concrete next tool+target to verify."
        )
    else:
        parts.append(
            "FORBIDDEN: paraphrase prior thoughts. Add ONE new fact OR change next_action. "
            "If you catch yourself rewriting 'write_file was blocked', STOP — pick the next protocol tool."
        )
    if any(k in blob for k in ("blocked", "not installed", "missing", "declare_apis", "bind_task")):
        parts.append(
            "Blocker already known. Do NOT restate it. next_action MUST advance: "
            "install_packages / ask_epistemic / web_research / fetch_url / write_file."
        )
    if force_next_tools:
        parts.append(
            "REQUIRED next_action tool (pick one): " + ", ".join(force_next_tools[:4]) + "."
        )
    if prior_actions:
        parts.append("Do NOT repeat next_action=" + prior_actions[-1] + ".")
    return " ".join(parts)


def _chain_step_text(payload: dict[str, Any], raw: str) -> str:
    thought = _as_text(payload.get("thought"))
    next_action = _as_text(payload.get("next_action"))
    facts = _as_str_list(payload.get("known_facts"))
    bits: list[str] = []
    if thought:
        bits.append(thought)
    if next_action:
        bits.append("next=" + next_action)
    if facts:
        bits.append("facts=" + "; ".join(facts[:4]))
    if bits:
        return " | ".join(bits)
    if payload:
        # Parsed fine but every field was a schema placeholder — nothing to report.
        return ""
    compact = " ".join(raw.split())
    return compact[:500] if compact else ""


def _chain_summary_text(payload: dict[str, Any], step_texts: list[str]) -> str:
    summary = _as_text(payload.get("summary"))
    if summary:
        next_action = _as_text(payload.get("next_action"))
        verify = _as_str_list(payload.get("verify_plan"))
        bits = [summary]
        if next_action:
            bits.append("next=" + next_action)
        if verify:
            bits.append("verify=" + "; ".join(verify[:5]))
        return " | ".join(bits)
    # Fallback: compress last step only — never dump the full chain to the main agent.
    if step_texts:
        return _one_line(step_texts[-1], 400)
    return ""


def _resolve_need(
    need: ReasoningNeed | str | None,
    reasoning_state: ReasoningState,
    context_state: Any,
) -> ReasoningNeed:
    if need is None:
        return classify_reasoning_need(reasoning_state.goal, context_state, reasoning_state)
    if isinstance(need, ReasoningNeed):
        return need
    return ReasoningNeed(str(need))


def _sync_failures_from_context(reasoning_state: ReasoningState, context_state: Any) -> None:
    results = getattr(context_state, "tool_results", None) or []
    lines: list[str] = []
    for entry in results:
        success = getattr(entry, "success", True)
        if isinstance(entry, dict):
            success = bool(entry.get("success", True))
            name = str(entry.get("tool_name", "tool"))
            error = str(entry.get("error") or entry.get("body") or "failed")
            path = str(entry.get("path") or "")
        else:
            name = str(getattr(entry, "tool_name", "tool"))
            error = str(getattr(entry, "error", None) or getattr(entry, "body", "") or "failed")
            path = ""
            call = getattr(entry, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            if isinstance(arguments, dict):
                path = str(arguments.get("path") or "")
        if success:
            continue
        label = f"{name}({path})" if path else name
        lines.append(f"{label}: {_one_line(error, 220)}")
    reasoning_state.append_unique("failed_attempts", lines, cap=20)


def _apply_short(state: ReasoningState, payload: dict[str, Any]) -> None:
    next_action = _as_text(payload.get("next_action"))
    if next_action:
        state.next_action = next_action
    state.append_unique("known_facts", _as_str_list(payload.get("known_facts")), cap=20)


def _apply_extended(state: ReasoningState, payload: dict[str, Any]) -> None:
    _apply_short(state, payload)
    state.append_unique("decisions", _as_str_list(payload.get("decisions")), cap=15)
    state.append_unique("assumptions", _as_str_list(payload.get("assumptions")), cap=12)
    state.append_unique("failed_attempts", _as_str_list(payload.get("failed_attempts")), cap=20)
    questions = _as_str_list(payload.get("open_questions"))
    if questions:
        state.open_questions = questions[-12:]


def _build_reasoning_prompt(
    state: ReasoningState,
    context_state: Any,
    need: ReasoningNeed,
    *,
    prior_thought: str = "",
) -> str:
    mode = "SHORT" if need is ReasoningNeed.SHORT else "EXTENDED"
    schema = (
        '{"next_action": "string", "known_facts": ["string"]}'
        if need is ReasoningNeed.SHORT
        else (
            '{"next_action": "string", "known_facts": ["string"], '
            '"decisions": ["string"], "assumptions": ["string"], '
            '"open_questions": ["string"], "failed_attempts": ["string"]}'
        )
    )
    snapshot = _context_snapshot(context_state)
    prior = _one_line(prior_thought, 320) if prior_thought.strip() else compress_reasoning_state(state, max_chars=260)
    if need is ReasoningNeed.SHORT:
        mode_hint = "Fill next_action and any new known_facts."
    else:
        mode_hint = "Update decisions, assumptions, open_questions, and next_action."

    return render_system_prompt(
        "cot",
        marker=REASONING_MARKER,
        mode=mode,
        goal=state.goal,
        snapshot=snapshot,
        prior=prior or "(empty)",
        schema=schema,
        mode_hint=mode_hint,
    )


def _context_snapshot(context_state: Any, *, max_chars: int = 1_200) -> str:
    lines: list[str] = []
    files = list(getattr(context_state, "relevant_files", None) or [])[-6:]
    if files:
        lines.append("files: " + ", ".join(str(path) for path in files))
    actions = list(getattr(context_state, "previous_actions", None) or [])[-4:]
    for action in actions:
        summary = getattr(action, "summary", action)
        iteration = getattr(action, "iteration", "?")
        lines.append(f"action[{iteration}]: {_one_line(str(summary), 120)}")
    feedback = str(getattr(context_state, "verification_feedback", "") or "").strip()
    if feedback:
        lines.append("verification: " + _one_line(feedback, 400))
    results = list(getattr(context_state, "tool_results", None) or [])[-4:]
    for entry in results:
        if isinstance(entry, dict):
            name = entry.get("tool_name", "tool")
            ok = entry.get("success", True)
            detail = entry.get("error") or entry.get("body") or ""
        else:
            name = getattr(entry, "tool_name", "tool")
            ok = getattr(entry, "success", True)
            detail = getattr(entry, "error", None) or getattr(entry, "body", "")
        status = "ok" if ok else "error"
        lines.append(f"result {name} ({status}): {_one_line(str(detail), 140)}")
    text = "\n".join(lines) or "(no context yet)"
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 14].rstrip() + "\n...[truncated]"


def _is_placeholder(value: str) -> bool:
    """True for values echoed straight from the JSON schema in the prompt."""
    compact = " ".join(str(value or "").split()).strip().strip("\"'[]<>").lower()
    return compact in _SCHEMA_PLACEHOLDERS


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    text = _one_line(str(value), 240)
    return "" if _is_placeholder(text) else text


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]
    return [item for item in items if item.strip() and not _is_placeholder(item)]


def _one_line(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _cycle_summary(state: ReasoningState) -> str:
    bits: list[str] = []
    if state.next_action.strip():
        bits.append("next=" + _one_line(state.next_action, 90))
    if state.known_facts:
        bits.append("fact=" + _one_line(state.known_facts[-1], 90))
    if state.decisions:
        bits.append("decision=" + _one_line(state.decisions[-1], 90))
    if state.failed_attempts:
        bits.append("avoid=" + _one_line(state.failed_attempts[-1], 90))
    return "; ".join(bits)


def _latest_cycle_summary(state: ReasoningState) -> str:
    if not state.cycle_summaries:
        return ""
    return state.cycle_summaries[-1]
