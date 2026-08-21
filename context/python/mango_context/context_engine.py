from __future__ import annotations

import json
from typing import Any, Callable, Iterable

from mango_context.ast_slice import slice_source
from mango_context.context_profile import CODER_PROFILE, ContextProfile
from mango_context.guard import ingest_result_into_memory, remember_file_slice
from mango_context.prompt_window import build_idle_retry_prompt, build_prompt
from mango_context.types import ContextBudget, ContextState, ToolSpec

SourceSlicer = Callable[..., str]


class ContextEngine:
    """Maintains ContextState and rebuilds a budgeted prompt each turn."""

    def __init__(
        self,
        goal: str,
        *,
        system_prompt: str = "",
        tool_instruction: str = "",
        tools: Iterable[ToolSpec | tuple[str, str]] | None = None,
        constraints: Iterable[str] | None = None,
        profile: ContextProfile | None = None,
        budget: ContextBudget | None = None,
        slicer: SourceSlicer | None = None,
    ) -> None:
        profile = profile or CODER_PROFILE
        self._slicer = slicer or slice_source
        self._state = ContextState(
            goal=goal.strip(),
            system_prompt=system_prompt,
            tool_instruction=tool_instruction,
            available_tools=[_as_tool_spec(item) for item in (tools or [])],
            budget=budget or profile.budget,
        )
        for constraint in constraints or []:
            self._state.add_constraint(constraint)

    @property
    def state(self) -> ContextState:
        return self._state

    def set_reasoning_summary(self, summary: str) -> None:
        self._state.reasoning_summary = summary.strip()

    def set_verification_feedback(self, report: str) -> None:
        self._state.verification_feedback = report.strip()

    def remember_file(self, path: str, source: str, *, iteration: int = 0) -> None:
        remember_file_slice(
            self._state,
            path,
            source,
            iteration=iteration,
            slicer=self._slicer,
        )

    def note_raw_result(
        self,
        iteration: int,
        tool_name: str,
        success: bool,
        body: str,
        *,
        error: str | None = None,
        paths: Iterable[str] | None = None,
    ) -> None:
        self._state.record_tool_result(iteration, tool_name, success, body, error=error)
        ingest_result_into_memory(
            self._state,
            tool_name=tool_name,
            body=body,
            paths=list(paths or []),
            iteration=iteration,
            slicer=self._slicer,
        )

    def build_prompt(self) -> str:
        return build_prompt(self._state)

    def build_idle_retry_prompt(self) -> str:
        return build_idle_retry_prompt(self._state)

    def record_turn(
        self,
        iteration: int,
        *,
        model_output: str,
        tool_results: Iterable[Any] | None = None,
    ) -> None:
        results = list(tool_results or [])
        if results:
            names = []
            for result in results:
                entry_name, success, body, error, paths = self._normalize_tool_result(result)
                names.append(f"{entry_name} ({'ok' if success else 'error'})")
                self._state.record_tool_result(
                    iteration,
                    entry_name,
                    success,
                    body,
                    error=error,
                )
                for path in paths:
                    self._state.note_file(path)
                ingest_result_into_memory(
                    self._state,
                    tool_name=entry_name,
                    body=body,
                    paths=paths,
                    iteration=iteration,
                    slicer=self._slicer,
                )
            self._state.record_action(iteration, "; ".join(names))
        else:
            summary = _one_line(model_output) or "final answer"
            self._state.record_action(iteration, summary)

    def _normalize_tool_result(self, result: Any) -> tuple[str, bool, str, str | None, list[str]]:
        if hasattr(result, "to_dict"):
            data = result.to_dict()
            call = getattr(result, "call", None)
        elif isinstance(result, dict):
            data = result
            call = None
        else:
            return "unknown", False, str(result), None, []

        name = str(data.get("tool_name") or "unknown")
        success = bool(data.get("success"))
        error = data.get("error")
        body = self._compact_output(data.get("output"), error)
        paths = _extract_paths(data.get("output"), call)
        return name, success, body, str(error) if error else None, paths

    def _compact_output(self, output: Any, error: Any) -> str:
        if error and output is None:
            return str(error)
        if isinstance(output, dict):
            if "content" in output:
                path = str(output.get("path", "") or "")
                content = str(output.get("content", "") or "")
                from mango_context.guard import focus_from_state

                sliced = self._slicer(
                    content,
                    path=path,
                    focus_symbols=focus_from_state(self._state),
                    body_lines=self._state.budget.body_lines,
                )
                prefix = f"path: {path}\n" if path else ""
                return prefix + sliced
            if "stdout" in output or "stderr" in output:
                return _compact_terminal(output)
            if "matches" in output:
                lines = [f"{output.get('match_count', len(output['matches']))} matches"]
                for match in output["matches"][:12]:
                    if isinstance(match, dict):
                        text = str(match.get("text", ""))
                        if len(text) > 80:
                            text = text[:77] + "..."
                        lines.append(f"{match.get('path')}:{match.get('line')}: {text}")
                    else:
                        lines.append(str(match)[:80])
                return "\n".join(lines)
            if "replacements" in output or "symbol" in output:
                return json.dumps(
                    {
                        k: output[k]
                        for k in ("path", "symbol", "kind", "replacements", "bytes_written", "syntax_error")
                        if k in output
                    },
                    ensure_ascii=False,
                )
            if "exists" in output and "evidence" in output:
                return json.dumps(output, ensure_ascii=False, separators=(",", ":"))
            return json.dumps(output, ensure_ascii=False)
        if output is None:
            return ""
        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=False)


def _as_tool_spec(item: ToolSpec | tuple[str, str]) -> ToolSpec:
    if isinstance(item, ToolSpec):
        return item
    name, description = item
    return ToolSpec(name=name, description=description)


def _compact_terminal(output: dict[str, Any]) -> str:
    stdout = str(output.get("stdout") or "")
    stderr = str(output.get("stderr") or "")
    parts = [f"exit_code: {output.get('exit_code')}"]
    tail = _tail_clip(stdout, 12)
    if tail:
        parts.append(tail)
    if stderr:
        parts.append("stderr:\n" + _tail_clip(stderr, 6))
    return "\n".join(parts).strip()


def _tail_clip(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = [f"... ({len(lines) - max_lines} more lines)"] + lines[-max_lines:]
    clipped = []
    for line in lines:
        clipped.append(line if len(line) <= 120 else line[:117] + "...")
    return "\n".join(clipped)


def _extract_paths(output: Any, call: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(output, dict):
        for key in ("path", "root"):
            value = output.get(key)
            if isinstance(value, str) and value:
                paths.append(value)
    arguments = getattr(call, "arguments", None)
    if isinstance(arguments, dict):
        value = arguments.get("path")
        if isinstance(value, str) and value:
            paths.append(value)
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _one_line(text: str, limit: int = 160) -> str:
    line = " ".join(text.strip().split())
    if len(line) <= limit:
        return line
    return line[: limit - 3] + "..."
