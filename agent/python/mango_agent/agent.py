from __future__ import annotations

import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from mango_codeintel import CodeIndex, register_codebase_lookup
from mango_context import ContextBudget, ContextEngine
from mango_cot import CoTEngine, compress_reasoning_state, extract_goal_targets, thought_for_ui
from mango_epistemic import EpistemicEngine, register_ask_epistemic
from mango_epistemic.parse import usable_api_brief, usable_api_signature
from mango_epistemic.targets import lookup_targets, output_covers
from mango_tools import ToolRegistry, create_default_registry, parse_tool_calls, run_tool_calls
from mango_tools.format import TOOL_CALL_PREFIX, tool_call_instruction
from mango_tools.gbnf import tool_call_gbnf
from mango_tools.paths import normalize_tool_path, resolve_tool_path
from mango_tools.syntax import collect_python_syntax_errors
from mango_tools.types import ToolCall, ToolResult
from mango_verification.ledger import VerificationLedger
from mango_verification.map_failures import map_failed_tests

from mango_agent.agent_context import AgentLimits
from mango_agent.thought_sanitize import strip_thought_markup
from mango_agent import events as agent_events
from mango_agent.design_review import (
    coarsen_after_read_message,
    lock_coarsened,
    review_message,
)
from mango_agent.experiment import (
    MAX_REVERTS,
    claimed_speedup_pct,
    decide_experiment,
    goal_wants_perf,
    hypothesis_from_thought,
    restore_snapshots,
)
from mango_agent.prompt import compose_agent_system_prompt, feedback, render_system_prompt
from mango_agent.thinking import thinking_preset, verify_hint_for
from mango_agent.types import AgentResult, AgentStep, LoopMetrics, ModelRunnerProtocol, StopReason

_CODE_MUTATING_TOOLS = frozenset({"write_file", "edit_file", "edit_symbol", "rename_symbol"})
_WORK_TOOLS = _CODE_MUTATING_TOOLS | {"run_tests", "run_terminal_command"}
_RESEARCH_TOOLS = frozenset({"web_research", "doc_lookup", "package_source_lookup"})
_ACTING_TOOLS = _WORK_TOOLS | _RESEARCH_TOOLS
_INSPECT_TOOLS = frozenset({"search_code", "read_file", "codebase_lookup", "ask_epistemic"})
_PLAN_READONLY = frozenset({"read_file", "search_code", "codebase_lookup"})
_PLAN_ALLOWED = _PLAN_READONLY | {"declare_apis", "ask_epistemic"}
_TEST_ONLY_LIBS = frozenset(
    {
        "unittest",
        "unittest.mock",
        "pytest",
        "mock",
        "doctest",
        "hypothesis",
        "nose",
        "nose2",
    }
)
_STDLIB_LIBS = frozenset(
    {
        "abc",
        "argparse",
        "array",
        "ast",
        "asyncio",
        "base64",
        "bisect",
        "builtins",
        "collections",
        "concurrent",
        "concurrent.futures",
        "contextlib",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "fnmatch",
        "functools",
        "glob",
        "hashlib",
        "heapq",
        "html",
        "http",
        "io",
        "itertools",
        "json",
        "logging",
        "math",
        "os",
        "pathlib",
        "pickle",
        "pprint",
        "queue",
        "random",
        "re",
        "secrets",
        "shlex",
        "shutil",
        "signal",
        "socket",
        "sqlite3",
        "statistics",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tempfile",
        "textwrap",
        "threading",
        "time",
        "traceback",
        "typing",
        "unicodedata",
        "urllib",
        "uuid",
        "warnings",
        "weakref",
        "xml",
        "zipfile",
    }
)
_THIRD_PARTY_LIBS = frozenset(
    {
        "aiohttp",
        "beautifulsoup",
        "beautifulsoup4",
        "boto3",
        "bs4",
        "django",
        "fastapi",
        "flask",
        "httpx",
        "lxml",
        "matplotlib",
        "numpy",
        "openai",
        "opencv",
        "pandas",
        "pillow",
        "pydantic",
        "pyyaml",
        "redis",
        "requests",
        "scikit-learn",
        "scipy",
        "seaborn",
        "sklearn",
        "sqlalchemy",
        "tensorflow",
        "torch",
        "typer",
    }
)
_FOLLOW_UP_MARKERS = (
    "you already changed files in this workspace",
    "follow-up request:",
)
_TEST_DIR_NAMES = frozenset({"tests", "testing", "test"})
_IDLE_TOOL_RETRIES = 2
_MAX_TEST_FIX_ATTEMPTS = 5  # messaging threshold only — loop stops at max_iterations/time, not here
_MAX_STRESS_NUDGES = 2
_WRITE_TOOL_MAX_TOKENS = 2048
_TRUNCATED_WRITE_TOOL_MAX_TOKENS = 3072
_MAX_REASONING_CYCLES_PER_ITER = 3
_CONCURRENCY_IMPL = re.compile(
    r"\b(threading|asyncio|concurrent\.futures|multiprocessing)\b|"
    r"\b(Lock|RLock|Semaphore|Event|Condition|Barrier|ThreadPoolExecutor|ProcessPoolExecutor)\s*\("
)
_CONCURRENCY_TEST = re.compile(
    r"\b(ThreadPoolExecutor|ProcessPoolExecutor|threading\.Thread|concurrent\.futures|"
    r"asyncio\.(gather|wait|run)|Barrier|Thread\s*\()"
)
_FENCE_RE = re.compile(r"```[\w+-]*\n.*?```", re.DOTALL)
_GOAL_WANTS_TESTS = re.compile(r"(?i)test_|pytest|\btests?\b|\bteste")
_GOAL_WANTS_FILE_IO = re.compile(
    r"(?i)\b(read|edit|replace|write|create|modify)\b.*\bfile\b|\bread the file\b|\bedit the file\b"
)
_GOAL_IMPLIES_EDIT = re.compile(
    r"(?i)\b(fix|bug|refactor|rename|implement|add|update|change|modify|patch|correct|repair)\b"
)
_EXPLORE_TOOLS = frozenset({"search_code", "read_file", "codebase_lookup", "declare_apis", "ask_epistemic"})
_MIN_SECONDS_FOR_REASONING = 0.5
_RENAME_GOAL = re.compile(
    r"\brename\s+([A-Za-z_][A-Za-z0-9_]*)\s+to\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_DEF_OR_CLASS = re.compile(
    r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]",
)


def normalize_model_output(text: str) -> str:
    """Strip common model artifacts before parsing tool calls."""
    cleaned = text.strip()
    for prefix in ("<channel|>", "<|channel|>"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].lstrip()
    return cleaned


class Agent:
    """
    Full main loop: ContextState -> CoT -> build_prompt -> model -> tools
    -> codebase_lookup / ask_epistemic / auto-verification + fix-loop.
    """

    def __init__(
        self,
        model_runner: ModelRunnerProtocol,
        *,
        tool_registry: ToolRegistry | None = None,
        system_prompt: str | None = None,
        limits: AgentLimits | None = None,
        max_iterations: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = 0.1,
        top_p: float | None = 0.95,
        max_prompt_chars: int | None = None,
        epistemic_web_backend: Any | None = None,
        codeintel_root: str | Path | None = None,
        verification_root: str | Path | None = None,
        verification_config: Any | None = None,
        max_fix_attempts: int | None = None,
        max_runtime_seconds: float | None = None,
        max_reasoning_cycles: int | None = None,
        max_epistemic_iterations: int | None = None,
        use_tool_grammar: bool = True,
        thought_max_tokens: int | None = None,
        tool_max_tokens: int | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        require_tools: bool = False,
        task_wants_tests: bool | None = None,
        plan_apis_first: bool = False,
        enable_declare_apis: bool = True,
        verbose: bool = False,
        disabled_tools: frozenset[str] | set[str] | None = None,
        research_targets: list[tuple[str, str]] | None = None,
        thinking_level: str | None = None,
    ) -> None:
        self._model = model_runner
        self._limits = _merge_limits(
            limits,
            max_iterations=max_iterations,
            max_prompt_chars=max_prompt_chars,
            max_fix_attempts=max_fix_attempts,
            max_runtime_seconds=max_runtime_seconds,
            max_reasoning_cycles=max_reasoning_cycles,
            max_epistemic_iterations=max_epistemic_iterations,
        )
        self._deadline: float | None = None
        self._disabled_tools = frozenset(disabled_tools or ())
        if tool_registry is None:
            self._registry = create_default_registry()
            self._epistemic: EpistemicEngine | None = register_ask_epistemic(
                self._registry,
                self._model,
                web_backend=epistemic_web_backend,
                max_iterations=self._limits.max_epistemic_iterations,
                get_deadline=lambda: self._deadline,
            )
            if "codebase_lookup" in self._disabled_tools:
                self._codeintel = None
            else:
                root = Path(codeintel_root) if codeintel_root else Path.cwd()
                self._codeintel = register_codebase_lookup(self._registry, root)
        else:
            self._registry = tool_registry
            self._epistemic = None
            self._codeintel = None
        self._thinking = thinking_preset(thinking_level)
        self._system_prompt = system_prompt or compose_agent_system_prompt(self._thinking.level)
        self._use_tool_grammar = use_tool_grammar
        self._max_tokens = max_tokens
        self._thought_max_tokens = (
            thought_max_tokens if thought_max_tokens is not None else self._thinking.thought_max_tokens
        )
        self._tool_max_tokens = tool_max_tokens
        self._write_tool_max_tokens = _WRITE_TOOL_MAX_TOKENS
        self._temperature = temperature
        self._top_p = top_p
        self._context: ContextEngine | None = None
        self._cot: CoTEngine | None = None
        self._verification_root = Path(verification_root).resolve() if verification_root else None
        self._verification_config = verification_config
        self._failed_verifications = 0
        self._verification_runs = 0
        self._reasoning_model_calls = 0
        self._last_verification_ok: bool | None = None
        self._last_verification_report = ""
        self._ledger = VerificationLedger()
        self._pending_symbol_lookups: list[str] = []
        self._pending_goal_files: list[str] = []
        self._pending_impl_files: list[str] = []
        self._ingested_workspace_tests = False
        self._rename_pair: tuple[str, str] | None = None
        self._run_started = 0.0
        self._on_event = on_event
        if self._epistemic is not None:
            self._epistemic.on_event = self._forward_epistemic_event
        self._require_tools = require_tools
        self._task_wants_tests_override = task_wants_tests
        self._plan_apis_first = plan_apis_first
        self._need_fix_cot = False
        self._verbose = verbose
        self._research_targets = list(research_targets or [])
        self._research_done: set[tuple[str, str]] = set()
        self._acted_once = False
        self._located_once = False
        self._inspected_once = False
        self._apis_declared_once = False
        self._epistemic_once = False
        self._declared_libraries: list[str] = []
        if enable_declare_apis:
            self._register_declare_apis()
        self._idle_tool_retries = 0
        self._readonly_iters = 0
        self._last_streamed = ""
        self._last_stream_channel = "thought"
        self._thought_log: list[str] = []
        self._thought_seq = 0
        self._task_wants_tests = False
        self._ran_tests_ok = False
        self._goal_wants_file_io = False
        self._run_tests_failures = 0
        self._runtime_smoke_failures = 0
        self._stress_nudges = 0
        self._prefer_write_file = False
        self._edit_fail_counts: dict[str, int] = {}
        self._review_needed = False
        self._review_done = False
        self._review_hold = 0
        self._review_paths: set[str] = set()
        self._lock_coarsened = False
        self._files_read: set[str] = set()
        self._impl_mutated_once = False
        self._greenfield_run = False
        self._current_iteration = 0
        self._cancel = threading.Event()
        self._step_tokens = 0
        self._syntax_emitted = False
        self._syntax_broken = False
        self._run_id = ""
        self._task = ""
        self._experiment_reverts = 0
        self._experiment_baseline: dict[str, Any] | None = None
        self._experiment_command: str | None = None
        self._experiment_exhausted = False
        self._experiment_locked_paths: set[str] = set()
        self._last_hypothesis = "this edit"

    @property
    def limits(self) -> AgentLimits:
        return self._limits

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._registry

    @property
    def model_runner(self) -> ModelRunnerProtocol:
        return self._model

    @property
    def context(self) -> ContextEngine | None:
        return self._context

    @property
    def cot(self) -> CoTEngine | None:
        return self._cot

    @property
    def epistemic(self) -> EpistemicEngine | None:
        return self._epistemic

    @property
    def codeintel(self) -> CodeIndex | None:
        return self._codeintel

    @property
    def failed_verifications(self) -> int:
        return self._failed_verifications

    def _register_declare_apis(self) -> None:
        if self._registry.has("declare_apis"):
            return

        def _declare(libraries: str, _context: dict[str, Any] | None = None) -> dict[str, Any]:
            names = _parse_libraries(libraries)
            if not names:
                raise ValueError(
                    "libraries must be a comma-separated list of library or API names, "
                    'e.g. "pandas, argparse, pathlib"'
                )
            self._declared_libraries = names
            self._apis_declared_once = True
            return {"ok": True, "libraries": names}

        self._registry.register(
            "declare_apis",
            _declare,
            description="Declare libraries/APIs before writing files.",
            parameters={
                "libraries": {
                    "type": "string",
                    "description": "Comma-separated library or API names",
                }
            },
            required=["libraries"],
        )

    def _plan_apis_enabled(self) -> bool:
        return bool(self._plan_apis_first)

    def _library_root(self, name: str) -> str:
        return str(name or "").split(".", 1)[0].strip().lower()

    def _is_stdlib_library(self, name: str) -> bool:
        raw = str(name or "").strip().lower()
        if not raw:
            return False
        if raw in _STDLIB_LIBS or raw in _TEST_ONLY_LIBS:
            return True
        return self._library_root(raw) in _STDLIB_LIBS

    def _non_stdlib_declared(self) -> list[str]:
        return [name for name in self._impl_declared_libraries() if not self._is_stdlib_library(name)]

    def _goal_third_party_libs(self) -> list[str]:
        blob = (self._task or "").lower()
        found: list[str] = []
        for name in sorted(_THIRD_PARTY_LIBS, key=len, reverse=True):
            if name in _TEST_ONLY_LIBS:
                continue
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", blob):
                found.append(name)
        return found

    def _libraries_needing_research(self) -> list[str]:
        declared = self._non_stdlib_declared()
        if declared:
            return declared
        return self._goal_third_party_libs()

    def _plan_gate_phase(self) -> str | None:
        if not self._plan_apis_enabled():
            return None
        needed = self._libraries_needing_research()
        if not needed:
            return None
        if not self._apis_declared_once:
            return "declare"
        if self._registry.has("ask_epistemic") and not self._epistemic_once:
            return "epistemic"
        return None

    def _impl_declared_libraries(self) -> list[str]:
        return [
            name
            for name in self._declared_libraries
            if name.lower() not in _TEST_ONLY_LIBS and not name.lower().startswith("unittest")
        ]

    def _plan_coverage_libraries(self) -> list[str]:
        """Third-party names that still need an epistemic brief. Stdlib never qualifies."""
        return list(self._non_stdlib_declared())

    def _epistemic_covers_plan(self, question: str, output: dict[str, Any] | None = None) -> bool:
        needed = self._plan_coverage_libraries()
        blob = (question or "").strip().lower()
        if output:
            looked = output.get("looked_up") or []
            if isinstance(looked, list):
                blob += " " + " ".join(str(item).lower() for item in looked)
            blob += " " + str(output.get("details") or "").lower()
        if not blob.strip():
            return False
        if not needed:
            return True
        return all(lib.lower() in blob for lib in needed)

    def _note_plan_progress(self, engine: ContextEngine, tool_results: list[ToolResult]) -> None:
        if not self._plan_apis_enabled():
            return
        for result in tool_results:
            if not result.success:
                continue
            if result.tool_name == "declare_apis":
                libs = ", ".join(self._impl_declared_libraries() or self._declared_libraries) or "the declared libraries"
                if self._libraries_needing_research():
                    engine.set_verification_feedback(feedback("declare", libs=libs))
                else:
                    self._epistemic_once = True
                    engine.set_verification_feedback(feedback("stdlib_ok", libs=libs))
            elif result.tool_name == "ask_epistemic":
                call = getattr(result, "call", None)
                arguments = getattr(call, "arguments", None) if call is not None else None
                question = ""
                if isinstance(arguments, dict):
                    question = str(arguments.get("question") or "")
                output = result.output if isinstance(result.output, dict) else {}
                useful = bool(
                    usable_api_brief(output.get("details"))
                    or usable_api_signature(output.get("signature"))
                    or output.get("exists") is False
                )
                if self._epistemic_covers_plan(question, output) and useful:
                    self._epistemic_once = True
                    self._apis_declared_once = True
                    engine.set_verification_feedback(feedback("epistemic_ok"))
                else:
                    needed = ", ".join(self._plan_coverage_libraries() or self._impl_declared_libraries()) or "the declared libraries"
                    engine.set_verification_feedback(feedback("epistemic_retry", needed=needed))

    def _research_still_required(self) -> bool:
        if not self._research_targets:
            return False
        return any(target not in self._research_done for target in self._research_targets)

    def _note_research_progress(self, engine: ContextEngine, tool_results: list[ToolResult]) -> None:
        if not self._research_targets:
            return
        for result in tool_results:
            output = result.output if isinstance(result.output, dict) else None
            if not result.success or output is None:
                continue
            for target in self._research_targets:
                if output_covers(output, target):
                    self._research_done.add(target)
        missing = [target for target in self._research_targets if target not in self._research_done]
        if missing:
            package, symbol = missing[0]
            example = f'{{"package": "{package}", "symbol": "{symbol}"}}'
            needed = ", ".join(f"{pkg}.{sym}" if sym else pkg for pkg, sym in missing)
            engine.set_verification_feedback(feedback("research_next", needed=needed, example=example))
        else:
            engine.set_verification_feedback(feedback("research_summarize"))

    def cancel(self) -> None:
        self._cancel.set()

    def _cancelled(self) -> bool:
        return self._cancel.is_set()

    def _visible_thought(self, text: str) -> tuple[str, bool]:
        return _sanitize_thought(
            text,
            max_sentences=self._thinking.thought_max_sentences,
            max_chars=self._thinking.thought_max_chars,
        )

    def _thought_id(self) -> str:
        return f"thought-{self._run_id}-{self._thought_seq}"

    def _close_thought_stream(self) -> None:
        """Finish the current Thought bubble so the next tools render below it."""
        if not self._run_id:
            return
        self._emit(
            agent_events.TOKEN,
            {
                "id": self._thought_id(),
                "delta": "",
                "channel": "thought",
                "done": True,
            },
        )
        self._thought_seq += 1
        self._thought_log = []

    def _emit_thought_text(self, text: str, *, duration_ms: int = 0, done: bool = False) -> None:
        visible = strip_thought_markup(text or "")
        if not visible:
            return
        self._thought_log = [visible]
        payload: dict[str, Any] = {
            "id": self._thought_id(),
            "delta": "",
            "text": "\n\n".join(self._thought_log) if self._thought_log else "",
            "channel": "thought",
            "duration_ms": duration_ms,
            "done": done,
        }
        self._emit(agent_events.TOKEN, payload)

    def _emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        if self._on_event is None:
            return
        data = dict(payload or {})
        if self._step_tokens:
            data["completion_tokens"] = self._step_tokens
            self._step_tokens = 0
        try:
            self._on_event({"event": event, "payload": data})
        except Exception:
            return

    def _forward_epistemic_event(self, message: dict[str, Any]) -> None:
        if self._on_event is None or not isinstance(message, dict):
            return
        event = str(message.get("event") or "")
        payload = dict(message.get("payload") or {})
        payload["subagent"] = "epistemic"
        if event == "agent.tool":
            payload["body"] = None
        elif event == "agent.token":
            if not payload.get("done"):
                return
        else:
            return
        try:
            self._on_event({"event": event, "payload": payload})
        except Exception:
            return

    def _trace(self, message: str) -> None:
        if not self._verbose:
            return
        print(f"[mango] {message}", file=sys.stderr, flush=True)

    def close_index(self) -> None:
        index = self._codeintel
        if index is None:
            return
        store = getattr(getattr(index, "indexer", None), "store", None)
        closer = getattr(store, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
        self._codeintel = None

    def close(self) -> None:
        self.close_index()
        unload = getattr(self._model, "unload", None)
        if callable(unload):
            unload()

    def run(
        self,
        task: str,
        *,
        system_prompt: str | None = None,
        deadline: float | None = None,
    ) -> AgentResult:
        self._run_started = time.monotonic()
        self._run_id = uuid.uuid4().hex[:10]
        self._task = task
        own_deadline = self._run_started + float(self._limits.max_runtime_seconds)
        self._deadline = min(deadline, own_deadline) if deadline is not None else own_deadline

        engine = ContextEngine(
            task,
            system_prompt=system_prompt or self._system_prompt,
            tool_instruction=tool_call_instruction(),
            tools=[]
            if self._plan_apis_first
            else [(schema.name, schema.description) for schema in self._registry.schemas()],
            budget=ContextBudget(
                max_chars=self._limits.max_prompt_chars,
                memory_max_chars=min(2_400, max(800, self._limits.max_prompt_chars // 16)),
                keep_recent_results=1 if self._plan_apis_first else 2,
            ),
        )
        cot = CoTEngine(
            task,
            short_max_tokens=self._thinking.cot_short,
            extended_max_tokens=self._thinking.cot_extended,
        )
        self._context = engine
        self._cot = cot
        self._failed_verifications = 0
        self._verification_runs = 0
        self._reasoning_model_calls = 0
        self._last_verification_ok = None
        self._last_verification_report = ""
        self._need_fix_cot = False
        self._ledger = VerificationLedger()
        targets = extract_goal_targets(task)
        self._pending_symbol_lookups = list(targets.symbols)
        self._pending_goal_files = list(targets.files)
        self._goal_wants_file_io = bool(_GOAL_WANTS_FILE_IO.search(task or ""))
        if self._require_tools:
            # UI create-from-scratch tasks should not scan/index the whole repo first.
            self._pending_symbol_lookups = []
        self._pending_impl_files = []
        self._ingested_workspace_tests = False
        self._syntax_emitted = False
        match = _RENAME_GOAL.search(task or "")
        self._rename_pair = (match.group(1), match.group(2)) if match else None
        self._acted_once = False
        self._located_once = False
        self._inspected_once = False
        self._apis_declared_once = False
        self._epistemic_once = False
        self._research_done = set()
        self._declared_libraries = []
        self._idle_tool_retries = 0
        self._readonly_iters = 0
        self._last_streamed = ""
        self._last_stream_channel = "thought"
        self._thought_log = []
        self._thought_seq = 0
        self._task_wants_tests = (
            self._task_wants_tests_override
            if self._task_wants_tests_override is not None
            else bool(_GOAL_WANTS_TESTS.search(task or ""))
        )
        self._ran_tests_ok = False
        self._run_tests_failures = 0
        self._runtime_smoke_failures = 0
        self._stress_nudges = 0
        self._prefer_write_file = False
        self._write_tool_max_tokens = _WRITE_TOOL_MAX_TOKENS
        self._edit_fail_counts = {}
        self._review_needed = False
        self._review_done = False
        self._review_hold = 0
        self._review_paths = set()
        self._lock_coarsened = False
        self._syntax_broken = False
        self._syntax_emitted = False
        self._files_read = set()
        self._impl_mutated_once = False
        self._greenfield_run = not self._impl_python_files() and not self._discover_test_files()
        self._experiment_reverts = 0
        self._experiment_baseline = None
        self._experiment_command = None
        self._experiment_exhausted = False
        self._experiment_locked_paths = set()
        self._last_hypothesis = "this edit"
        if self._plan_apis_enabled():
            if _is_follow_up_goal(task):
                self._apis_declared_once = True
                engine.set_verification_feedback(feedback("follow_up"))
            elif self._libraries_needing_research():
                engine.set_verification_feedback(feedback("declare_first"))
        steps: list[AgentStep] = []
        final_answer = ""
        idle_retry = False
        self._cancel.clear()
        started: dict[str, Any] = {"goal": task}
        if self._verification_root is not None:
            started["workspace"] = str(self._verification_root)
        self._emit(agent_events.STARTED, started)

        for iteration in range(1, self._limits.max_iterations + 1):
            self._current_iteration = iteration
            if self._review_hold:
                self._review_hold -= 1
            self._trace(f"iter {iteration}/{self._limits.max_iterations}")
            if self._cancelled():
                return self._result(
                    final_answer=final_answer,
                    steps=steps,
                    iterations=max(iteration - 1, 0),
                    stop_reason=StopReason.CANCELLED,
                    error="cancelled",
                )
            if self._timed_out():
                return self._result(
                    final_answer=final_answer,
                    steps=steps,
                    iterations=max(iteration - 1, 0),
                    stop_reason=StopReason.TIMEOUT,
                    error="time limit exceeded",
                )
            test_deadline = 24 if self._plan_apis_enabled() else 8
            if (
                self._require_tools
                and self._task_wants_tests
                and not self._ran_tests_ok
                and iteration >= min(test_deadline, self._limits.max_iterations)
            ):
                return self._result(
                    final_answer=final_answer or feedback("run.tests_deadline"),
                    steps=steps,
                    iterations=iteration,
                    stop_reason=StopReason.ERROR,
                    error=feedback("run.tests_deadline"),
                )
            if self._verification_enabled() and self._last_verification_ok is True:
                return self._complete(
                    steps=steps,
                    iterations=max(iteration - 1, 0),
                    draft=final_answer,
                )

            self._run_pending_lookups(engine, iteration)
            self._seed_static_syntax(engine)
            summary_limit = 900 if self._require_tools else 360

            allow_reason = (
                self._reasoning_model_calls < self._limits.max_reasoning_cycles
                and self._remaining_seconds() > _MIN_SECONDS_FOR_REASONING
                and not idle_retry
                and (
                    self._thinking.level != "off"
                    or not self._plan_apis_first
                )
                and self._plan_gate_phase() is None
                and not self._syntax_broken
            )
            # SWE-bench may run classic CoT cycles. GUI with thinking≠off uses chained CoT.
            budget_need_value: str | None = None
            summary = compress_reasoning_state(cot.state, max_chars=summary_limit)
            reasoning_cycles_this_iter = 0
            last_cycle_summary = ""

            if (
                allow_reason
                and self._thinking.chain_steps > 0
                and (
                    iteration == 1
                    or self._need_fix_cot
                    or self._thinking.verify_strength >= 3
                )
            ):
                chain_budget = max(
                    0,
                    self._limits.max_reasoning_cycles - self._reasoning_model_calls,
                )
                # chain_steps + 1 summarize call (do not shadow AgentStep list `steps`)
                n_chain = min(self._thinking.chain_steps, max(0, chain_budget - 1))
                if n_chain > 0:
                    cycle_started = time.monotonic()
                    hint = verify_hint_for(self._thinking.verify_strength)
                    if self._need_fix_cot:
                        hint = (
                            (hint + " ") if hint else ""
                        ) + "Prior verification failed. Focus on Fix → Verify again."

                    def _on_chain_step(step_i: int, text: str) -> None:
                        visible, _ = self._visible_thought(text)
                        if not visible:
                            return
                        self._emit_thought_text(
                            visible,
                            duration_ms=int((time.monotonic() - cycle_started) * 1000),
                        )

                    try:
                        final_summary = cot.run_chained(
                            self._model,
                            steps=n_chain,
                            verify_level=self._thinking.level,
                            verify_hint=hint,
                            context_state=engine.state,
                            max_tokens=self._thinking.cot_extended,
                            on_step=_on_chain_step,
                            should_cancel=self._cancelled,
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._trace(f"iter {iteration} chained cot failed: {exc}")
                        self._emit(
                            agent_events.ERROR,
                            {"text": f"thinking failed: {exc}"},
                        )
                        final_summary = ""
                        n_chain = 0

                    # Count step completions + summarize as reasoning model calls.
                    if n_chain > 0:
                        self._reasoning_model_calls += n_chain + 1
                        reasoning_cycles_this_iter = n_chain + 1
                    self._need_fix_cot = False
                    summary = final_summary or compress_reasoning_state(
                        cot.state, max_chars=summary_limit
                    )
                    if self._thinking.verify_strength >= 1:
                        vf = verify_hint_for(self._thinking.verify_strength)
                        if vf:
                            summary = f"{vf}\n{summary}".strip()
                    engine.set_reasoning_summary(summary)
                    self._trace(
                        f"iter {iteration} chained cot steps={n_chain}"
                        f" level={self._thinking.level}"
                        f" summary={summary.replace(chr(10), ' ')[:220]!r}"
                    )
                    if final_summary:
                        visible, _ = self._visible_thought(final_summary)
                        if visible:
                            self._emit_thought_text(
                                f"[summary] {visible.strip()}",
                                duration_ms=int((time.monotonic() - cycle_started) * 1000),
                            )
                    allow_reason = False  # classic per-cycle loop skipped this iter

            reasoning_cycle_limit = _MAX_REASONING_CYCLES_PER_ITER if self._inspect_before_edit() else 1
            while (
                allow_reason
                and self._reasoning_model_calls < self._limits.max_reasoning_cycles
                and reasoning_cycles_this_iter < reasoning_cycle_limit
                and not self._plan_apis_first
            ):
                state_before = json.dumps(
                    {
                        "known_facts": list(cot.state.known_facts),
                        "decisions": list(cot.state.decisions),
                        "assumptions": list(cot.state.assumptions),
                        "failed_attempts": list(cot.state.failed_attempts),
                        "open_questions": list(cot.state.open_questions),
                        "next_action": cot.state.next_action,
                    },
                    sort_keys=True,
                )
                cycle_started = time.monotonic()
                cot.run_cycle(engine.state, self._model, allow_model=True)
                if cot.last_need.value == "none":
                    break
                state_after = json.dumps(
                    {
                        "known_facts": list(cot.state.known_facts),
                        "decisions": list(cot.state.decisions),
                        "assumptions": list(cot.state.assumptions),
                        "failed_attempts": list(cot.state.failed_attempts),
                        "open_questions": list(cot.state.open_questions),
                        "next_action": cot.state.next_action,
                    },
                    sort_keys=True,
                )
                if state_after == state_before:
                    self._trace(
                        f"iter {iteration} cot no new state at cycle {reasoning_cycles_this_iter + 1}; stopping early"
                    )
                    break
                trace_summary = ""
                if cot.trace.entries:
                    trace_summary = str(cot.trace.entries[-1].get("summary") or "").strip()
                if trace_summary and trace_summary == last_cycle_summary:
                    self._trace(
                        f"iter {iteration} cot stalled at cycle {reasoning_cycles_this_iter + 1}; stopping early"
                    )
                    break
                self._reasoning_model_calls += 1
                reasoning_cycles_this_iter += 1
                budget_need_value = cot.last_need.value
                if trace_summary:
                    last_cycle_summary = trace_summary

                summary = compress_reasoning_state(cot.state, max_chars=summary_limit)
                engine.set_reasoning_summary(summary)
                self._trace(
                    f"iter {iteration} cot cycle {reasoning_cycles_this_iter}"
                    f" need={cot.last_need.value} summary={summary.replace(chr(10), ' ')[:220]!r}"
                )
                visible, _ = self._visible_thought(thought_for_ui(cot.state))
                if visible:
                    self._emit_thought_text(
                        visible,
                        duration_ms=int((time.monotonic() - cycle_started) * 1000),
                    )

                # Re-evaluate remaining time for potential additional cycles.
                allow_reason = (
                    self._reasoning_model_calls < self._limits.max_reasoning_cycles
                    and self._remaining_seconds() > _MIN_SECONDS_FOR_REASONING
                    and not idle_retry
                )

            # Always set a (possibly empty) reasoning summary for the action prompt.
            summary = compress_reasoning_state(cot.state, max_chars=summary_limit)
            engine.set_reasoning_summary(summary)
            if reasoning_cycles_this_iter == 0:
                self._trace(f"iter {iteration} cot skipped need={cot.last_need.value}")
            prompt = engine.build_idle_retry_prompt() if idle_retry else engine.build_prompt()
            try:
                force_tool = self._needs_tool()
                grammar = self._action_grammar()
                tool_names = self._action_tool_names() if grammar else []
                thought_id = self._thought_id()
                stream_started = time.monotonic()
                stream_buf: list[str] = []
                channel = "thought" if force_tool else "assistant"
                stream_phase = "thought"
                last_visible = ""

                def on_token(delta: str, _channel: str = channel, _id: str = thought_id) -> None:
                    nonlocal last_visible
                    if not delta:
                        return
                    if stream_phase != "thought":
                        return
                    stream_buf.append(delta)
                    joined = "".join(stream_buf)
                    visible = strip_thought_markup(joined)
                    if not visible.strip():
                        return
                    if len(visible) >= len(last_visible) and visible.startswith(last_visible):
                        out_delta = visible[len(last_visible) :]
                    else:
                        out_delta = visible
                        last_visible = ""
                    if not out_delta:
                        return
                    last_visible = visible
                    self._emit(
                        agent_events.TOKEN,
                        {
                            "id": _id,
                            "delta": out_delta,
                            "channel": _channel,
                            "duration_ms": int((time.monotonic() - stream_started) * 1000),
                            "done": False,
                        },
                    )

                def on_phase(name: str) -> None:
                    nonlocal stream_phase
                    stream_phase = "tool" if name == "tool_grammar" else "thought"

                if self._cancelled():
                    return self._result(
                        final_answer=final_answer,
                        steps=steps,
                        iterations=max(iteration - 1, 0),
                        stop_reason=StopReason.CANCELLED,
                        error="cancelled",
                    )

                effective_thought_max_tokens = int(
                    self._thought_max_tokens or self._thinking.thought_max_tokens
                )
                # Do not inflate past the configured cap. GUI used to bump this to 768
                # on every tool turn, which made a short thought take ~30s of sampling.

                completion = self._model.complete(
                    prompt,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    top_p=self._top_p,
                    reset_cache=iteration == 1,
                    grammar=grammar,
                    grammar_trigger=TOOL_CALL_PREFIX if grammar else None,
                    thought_max_tokens=effective_thought_max_tokens,
                    tool_max_tokens=self._effective_tool_max_tokens(tool_names),
                    force_grammar=bool(grammar) and force_tool,
                    on_token=on_token if self._on_event is not None else None,
                    on_phase=on_phase if self._on_event is not None else None,
                    should_cancel=self._cancelled,
                )
                model_output = normalize_model_output(str(completion.text))
                self._step_tokens = int(getattr(completion, "completion_tokens", 0) or 0)
                raw_thought = "".join(stream_buf)
                display_thought, had_code = self._visible_thought(raw_thought)
                self._last_streamed = display_thought
                self._last_stream_channel = channel
                if display_thought.strip() and display_thought != last_visible.strip():
                    tail = (
                        display_thought[len(last_visible) :]
                        if last_visible and display_thought.startswith(last_visible)
                        else display_thought
                    )
                    if tail.strip():
                        self._emit(
                            agent_events.TOKEN,
                            {
                                "id": thought_id,
                                "delta": tail,
                                "channel": channel,
                                "duration_ms": int((time.monotonic() - stream_started) * 1000),
                                "done": False,
                            },
                        )
                if self._cancelled():
                    self._close_thought_stream()
                    return self._result(
                        final_answer=final_answer,
                        steps=steps,
                        iterations=max(iteration - 1, 0),
                        stop_reason=StopReason.CANCELLED,
                        error="cancelled",
                    )
                if "```" in raw_thought or _looks_like_script(raw_thought):
                    engine.set_verification_feedback(feedback("thought_has_code"))
                elif _thought_sentence_count(display_thought) > self._thinking.thought_max_sentences:
                    engine.set_verification_feedback(feedback("thought_too_long"))
            except Exception as exc:  # noqa: BLE001
                return self._result(
                    final_answer=final_answer,
                    steps=steps,
                    iterations=iteration,
                    stop_reason=StopReason.ERROR,
                    error=str(exc),
                )

            tool_calls = parse_tool_calls(model_output)
            if self._disabled_tools:
                dropped = [call.name for call in tool_calls if call.name in self._disabled_tools]
                tool_calls = [call for call in tool_calls if call.name not in self._disabled_tools]
                if dropped and not tool_calls:
                    self._trace(f"iter {iteration} ignored disabled tools={dropped}")
                    engine.set_verification_feedback(
                        feedback("disabled_tools", dropped=", ".join(dropped))
                    )
                    idle_retry = True
                    steps.append(
                        self._record_step(
                            engine,
                            iteration,
                            prompt=prompt,
                            model_output=model_output,
                            reasoning_need=cot.last_need.value,
                            reasoning_summary=summary,
                        )
                    )
                    continue
            if not tool_calls:
                idle_retry = True
                preview = model_output.replace("\n", " ").strip()
                if len(preview) > 240:
                    preview = preview[:239] + "…"
                truncated = TOOL_CALL_PREFIX in model_output
                if truncated:
                    self._write_tool_max_tokens = max(
                        self._write_tool_max_tokens, _TRUNCATED_WRITE_TOOL_MAX_TOKENS
                    )
                    self._prefer_write_file = True
                self._trace(
                    f"iter {iteration} no tool call"
                    + (" (truncated/invalid JSON)" if truncated else "")
                    + (f" raw={preview!r}" if preview else "")
                )
                if self._verification_enabled() and self._last_verification_ok is not True:
                    if self._last_verification_ok is None and not self._syntax_errors():
                        self._execute_verification(engine, iteration)
                    steps.append(
                        self._record_step(
                            engine,
                            iteration,
                            prompt=prompt,
                            model_output=model_output,
                            reasoning_need=cot.last_need.value,
                            reasoning_summary=summary,
                        )
                    )
                    final_answer = model_output
                    if self._last_verification_ok is True:
                        return self._result(
                            final_answer=model_output,
                            steps=steps,
                            iterations=iteration,
                            stop_reason=StopReason.COMPLETED,
                        )
                    next_edit = getattr(engine.state, "verification_next_edit", "") or ""
                    current_source = getattr(engine.state, "verification_current_source", "") or ""
                    extra_edit = f"\nNext best edit: {next_edit}" if next_edit else ""
                    extra_snap = (
                        f"\nImplementation snapshot:\n{current_source[:700]}" if current_source else ""
                    )
                    engine.set_verification_feedback(
                        feedback(
                            "verification_fix",
                            report=self._last_verification_report or "Verification has not passed.",
                            next_edit=extra_edit,
                            snapshot=extra_snap,
                        )
                    )
                    continue
                if self._syntax_broken:
                    steps.append(
                        self._record_step(
                            engine,
                            iteration,
                            prompt=prompt,
                            model_output=model_output,
                            reasoning_need=cot.last_need.value,
                            reasoning_summary=summary,
                        )
                    )
                    final_answer = model_output
                    engine.set_verification_feedback(
                        feedback(
                            "syntax_broken",
                            report=self._last_verification_report or "Python syntax check failed.",
                        )
                    )
                    continue
                if self._tests_still_required():
                    auto_results = self._run_workspace_tests(iteration)
                    if auto_results:
                        self._handle_run_tests_results(auto_results, engine)
                        self._emit_tool_events([], auto_results, {}, skip_files=True)
                        steps.append(
                            self._record_step(
                                engine,
                                iteration,
                                prompt=prompt,
                                model_output=model_output,
                                reasoning_need=cot.last_need.value,
                                reasoning_summary=summary,
                                tool_results=auto_results,
                            )
                        )
                        if self._ran_tests_ok and not self._design_review_blocked():
                            return self._complete(
                                steps=steps,
                                iterations=iteration,
                            )
                    continue
                if self._design_review_still_required():
                    steps.append(
                        self._record_step(
                            engine,
                            iteration,
                            prompt=prompt,
                            model_output=model_output,
                            reasoning_need=cot.last_need.value,
                            reasoning_summary=summary,
                        )
                    )
                    engine.set_verification_feedback(review_message(coarsened=self._lock_coarsened))
                    continue
                if self._needs_tool() and self._idle_tool_retries < _IDLE_TOOL_RETRIES:
                    self._idle_tool_retries += 1
                    steps.append(
                        self._record_step(
                            engine,
                            iteration,
                            prompt=prompt,
                            model_output=model_output,
                            reasoning_need=cot.last_need.value,
                            reasoning_summary=summary,
                        )
                    )
                    final_answer = model_output
                    if truncated:
                        self._prefer_write_file = True
                    engine.set_verification_feedback(
                        feedback("truncated_json") if truncated else feedback("emit_tool")
                    )
                    continue
                if self._require_tools and not self._acted_once:
                    steps.append(
                        self._record_step(
                            engine,
                            iteration,
                            prompt=prompt,
                            model_output=model_output,
                            reasoning_need=cot.last_need.value,
                            reasoning_summary=summary,
                        )
                    )
                    final_answer = model_output
                    engine.set_verification_feedback(
                        feedback("no_edit_truncated") if truncated else feedback("no_edit")
                    )
                    continue
                steps.append(
                    self._record_step(
                        engine,
                        iteration,
                        prompt=prompt,
                        model_output=model_output,
                        reasoning_need=cot.last_need.value,
                        reasoning_summary=summary,
                    )
                )
                if self._tests_still_required() or self._syntax_broken:
                    engine.set_verification_feedback(
                        feedback("tests_still_red")
                        if self._tests_still_required()
                        else feedback(
                            "syntax_broken",
                            report=self._last_verification_report or "Python syntax check failed.",
                        )
                    )
                    continue
                return self._complete(
                    steps=steps,
                    iterations=iteration,
                    draft=model_output,
                )

            idle_retry = False
            self._idle_tool_retries = 0
            for call in tool_calls:
                self._trace(f"iter {iteration} tool={call.name} {_compact_args(call.arguments)}")
            snapshots = self._snapshot_paths(tool_calls)
            pending_tools = [call.name for call in tool_calls]
            self._last_hypothesis = hypothesis_from_thought(" ".join(self._thought_log))
            will_mutate = any(call.name in _CODE_MUTATING_TOOLS for call in tool_calls)
            if will_mutate:
                self._maybe_capture_perf_baseline()
            # Close the Thought bubble before tool chips so order is chronological.
            self._close_thought_stream()
            for call_i, call in enumerate(tool_calls):
                tool_name = call.name
                args = call.arguments if isinstance(call.arguments, dict) else {}
                stream_id = f"tool-{tool_name}-{self._run_id}-{iteration}-{call_i}"
                if tool_name == "run_tests":
                    self._emit(
                        agent_events.TOOL,
                        {
                            "id": f"tool-run-tests-{self._run_id}-{iteration}",
                            "name": tool_name,
                            "title": "Running tests…",
                            "streaming": True,
                            "console": True,
                        },
                    )
                elif tool_name == "ask_epistemic":
                    self._emit(
                        agent_events.TOOL,
                        {
                            "id": f"tool-ask-epistemic-{self._run_id}-{iteration}",
                            "name": tool_name,
                            "title": "Asked epistemic sub-agent",
                            "streaming": True,
                        },
                    )
                elif tool_name == "declare_apis":
                    self._emit(
                        agent_events.TOOL,
                        {
                            "id": f"tool-declare-apis-{self._run_id}-{iteration}",
                            "name": tool_name,
                            "title": "Declaring APIs…",
                            "streaming": True,
                        },
                    )
                elif tool_name in {
                    "search_code",
                    "read_file",
                    "run_terminal_command",
                    "measure",
                    "codebase_lookup",
                }:
                    title = agent_events.tool_title(tool_name, args)
                    if not title.endswith("…"):
                        title = f"{title}…"
                    self._emit(
                        agent_events.TOOL,
                        {
                            "id": stream_id,
                            "name": tool_name,
                            "title": title,
                            "streaming": True,
                            "console": tool_name in {"run_terminal_command", "measure"},
                        },
                    )
            tool_results = self._execute_tool_calls(tool_calls)
            if self._cancelled():
                return self._result(
                    final_answer=final_answer,
                    steps=steps,
                    iterations=max(iteration - 1, 0),
                    stop_reason=StopReason.CANCELLED,
                    error="cancelled",
                )
            tool_results = self._reject_fuzzy_edits(tool_results)
            tool_results = self._fallback_failed_edits(tool_results)
            self._note_review_reads(engine, tool_results)
            self._note_read_files(tool_results)
            for result in tool_results:
                if result.success:
                    self._trace(f"iter {iteration} {result.tool_name} ok {_compact_result(result)}")
                else:
                    self._trace(f"iter {iteration} {result.tool_name} FAIL {result.error}")
            if any(
                result.success
                and result.tool_name in _INSPECT_TOOLS
                and self._inspect_result_is_useful(result)
                for result in tool_results
            ):
                self._inspected_once = True
            if any(
                result.success
                and result.tool_name == "search_code"
                and self._search_found_impl(result)
                for result in tool_results
            ):
                self._located_once = True
            if any(
                result.success
                and result.tool_name == "codebase_lookup"
                and self._codebase_lookup_found_impl(result)
                for result in tool_results
            ):
                self._located_once = True
            mutated = any(
                result.success and result.tool_name in _CODE_MUTATING_TOOLS for result in tool_results
            )
            if mutated:
                self._readonly_iters = 0
                self._clear_edit_failures(tool_results)
                self._arm_design_review_state(tool_results, snapshots)
            else:
                self._readonly_iters += 1
            if self._require_tools:
                self._feedback_failed_tools(engine, tool_results)
            self._note_plan_progress(engine, tool_results)
            self._note_research_progress(engine, tool_results)
            if any(result.success and result.tool_name in _ACTING_TOOLS for result in tool_results):
                self._acted_once = True
            self._note_impl_mutations(tool_results)
            self._emit_file_events(tool_results, snapshots)
            syntax_bad = self._enforce_syntax_after_mutation(
                engine, tool_results, iteration, snapshots
            )
            if not syntax_bad:
                self._handle_run_tests_results(tool_results, engine)
            auto_results = [] if syntax_bad else self._auto_run_tests_if_needed(tool_results, iteration)
            if auto_results:
                tool_results = [*tool_results, *auto_results]
                self._handle_run_tests_results(auto_results, engine)
            reverted = self._conclude_experiment(
                engine,
                snapshots,
                tool_results,
                syntax_bad=syntax_bad,
                iteration=iteration,
            )
            if reverted:
                syntax_bad = False
            if not reverted and not syntax_bad and self._run_tests_failures == 0:
                if self._design_review_still_required():
                    engine.set_verification_feedback(
                        review_message(coarsened=self._lock_coarsened)
                    )
                elif self._review_hold == 0 and self._stress_nudges == 0:
                    self._note_repo_impact(engine, tool_results)
            if (
                not reverted
                and self._require_tools
                and self._task_wants_tests
                and self._ran_tests_ok
                and not self._syntax_broken
                and not self._design_review_blocked()
            ):
                self._emit_tool_events(tool_calls, tool_results, snapshots, skip_files=True)
                steps.append(
                    self._record_step(
                        engine,
                        iteration,
                        prompt=prompt,
                        model_output=model_output,
                        reasoning_need=cot.last_need.value,
                        reasoning_summary=summary,
                        tool_calls=tool_calls,
                        tool_results=tool_results,
                    )
                )
                return self._complete(
                    steps=steps,
                    iterations=iteration,
                )
            self._emit_tool_events(tool_calls, tool_results, snapshots, skip_files=True)
            steps.append(
                self._record_step(
                    engine,
                    iteration,
                    prompt=prompt,
                    model_output=model_output,
                    reasoning_need=cot.last_need.value,
                    reasoning_summary=summary,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                )
            )
            final_answer = model_output
            verification_result = self._maybe_verify(engine, iteration, tool_results)
            if verification_result is not None and self._rename_still_needed():
                if self._apply_pending_rename(engine, iteration):
                    verification_result = self._execute_verification(engine, iteration)
            if verification_result is not None and verification_result.success:
                if self._rename_still_needed():
                    self._block_incomplete_rename(engine)
                else:
                    return self._complete(
                        steps=steps,
                        iterations=iteration,
                        draft=model_output,
                        verification_report=self._last_verification_report,
                    )
            if (
                verification_result is not None
                and not verification_result.success
                and self._failed_verifications >= self._limits.max_fix_attempts
            ):
                report = self._abort_report()
                return self._result(
                    final_answer=report,
                    steps=steps,
                    iterations=iteration,
                    stop_reason=StopReason.VERIFICATION_FAILED,
                    error=report,
                    verification_report=self._last_verification_report or report,
                )
            if self._require_tools and self._readonly_iters >= 3 and not self._acted_once:
                if self._inspect_before_edit() and not self._inspected_once:
                    if self._readonly_iters >= 4:
                        self._inspected_once = True
                    engine.set_verification_feedback(feedback("readonly_no_impl"))
                else:
                    engine.set_verification_feedback(feedback("readonly_edit_now"))

        return self._result(
            final_answer=final_answer or self._fallback_summary(steps),
            steps=steps,
            iterations=self._limits.max_iterations,
            stop_reason=(
                StopReason.ERROR if self._tests_still_required() or self._syntax_broken else StopReason.MAX_ITERATIONS
            ),
            error=(
                feedback("tests_deadline")
                if self._tests_still_required()
                else (
                    feedback("syntax_broken", report=self._last_verification_report or "Python syntax check failed.")
                    if self._syntax_broken
                    else None
                )
            ),
        )

    def _remaining_seconds(self) -> float:
        if self._deadline is None:
            return float(self._limits.max_runtime_seconds)
        return self._deadline - time.monotonic()

    def _timed_out(self) -> bool:
        return self._remaining_seconds() <= 0

    def _finish_allowed(self) -> bool:
        if self._syntax_broken:
            return False
        if self._tests_still_required():
            return False
        if self._design_review_still_required() or self._review_hold > 0:
            return False
        if (
            self._grounded_edits_enabled()
            and self._acted_once
            and not self._impl_mutated_once
            and not self._ran_tests_ok
        ):
            return False
        if (
            self._thinking.verify_strength >= 2
            and self._verification_enabled()
            and self._acted_once
            and self._impl_mutated_once
            and self._last_verification_ok is not True
        ):
            return False
        return True

    def _complete(
        self,
        *,
        steps: list[AgentStep],
        iterations: int,
        draft: str = "",
        verification_report: str | None = None,
    ) -> AgentResult:
        if not self._finish_allowed():
            facts = self._finish_facts(steps)
            answer = self._fallback_summary(steps, draft=draft)
            if (
                self._grounded_edits_enabled()
                and self._acted_once
                and not self._impl_mutated_once
                and not self._ran_tests_ok
            ):
                err = feedback("no_impl_change")
            else:
                err = feedback("tests_still_red")
            return self._result(
                final_answer=answer,
                steps=steps,
                iterations=iterations,
                stop_reason=StopReason.ERROR,
                error=err,
                verification_report=verification_report,
            )
        answer = self._write_finish_summary(steps, draft=draft)
        return self._result(
            final_answer=answer,
            steps=steps,
            iterations=iterations,
            stop_reason=StopReason.COMPLETED,
            verification_report=verification_report,
        )

    def _write_finish_summary(self, steps: list[AgentStep], *, draft: str = "") -> str:
        fallback = self._fallback_summary(steps, draft=draft)
        cleaned = _clean_finish_summary(draft)
        if not self._plan_apis_enabled():
            stub = cleaned.lower().strip()
            if cleaned and "<tool_call" not in stub and stub not in {"done", "all done.", "all tests passed.", "all tests passed"}:
                return cleaned
            return fallback
        facts = self._finish_facts(steps)
        try:
            prompt = render_system_prompt("summary", goal=self._task or "", facts=facts)
            completion = self._model.complete(
                prompt,
                max_tokens=self._thinking.summary_max_tokens,
                temperature=0.2,
                reset_cache=True,
            )
            text = _clean_finish_summary(str(getattr(completion, "text", "") or ""))
        except Exception:
            text = ""
        if _is_good_finish_summary(text) and not _finish_lies_about_tests(text, self._ran_tests_ok):
            return text
        return fallback

    def _finish_facts(self, steps: list[AgentStep]) -> str:
        files: list[str] = []
        seen: set[str] = set()
        tests_ok = self._ran_tests_ok
        for step in steps:
            for result in getattr(step, "tool_results", None) or []:
                if not result.success or result.tool_name not in _CODE_MUTATING_TOOLS:
                    continue
                output = result.output if isinstance(result.output, dict) else {}
                raw = str(output.get("path") or output.get("absolute_path") or "")
                call = getattr(result, "call", None)
                arguments = getattr(call, "arguments", None) if call is not None else None
                if not raw and isinstance(arguments, dict):
                    raw = str(arguments.get("path") or "")
                name = Path(raw).name if raw else ""
                if name and name not in seen:
                    seen.add(name)
                    files.append(name)
        tests_ok = self._ran_tests_ok
        if tests_ok:
            tests = "passed"
        elif self._run_tests_failures >= _MAX_TEST_FIX_ATTEMPTS:
            tests = f"still failing after {_MAX_TEST_FIX_ATTEMPTS}+ runs"
        else:
            tests = "not confirmed"
        changed = ", ".join(files) if files else "no files recorded"
        syntax = "broken" if self._syntax_broken else "ok"
        goal = " ".join((self._task or "").split())
        if len(goal) > 400:
            goal = goal[:397] + "..."
        return (
            f"changed_files: {changed}\n"
            f"tests: {tests}\n"
            f"syntax: {syntax}\n"
            f"goal: {goal or '(none)'}"
        )

    def _fallback_summary(self, steps: list[AgentStep], *, draft: str = "") -> str:
        facts = self._finish_facts(steps)
        files = "the code"
        if "changed_files: " in facts:
            raw = facts.split("changed_files: ", 1)[1].split("\n", 1)[0].strip()
            if raw and raw != "no files recorded":
                files = raw
        if self._ran_tests_ok:
            tests = "Tests passed."
        elif self._run_tests_failures >= _MAX_TEST_FIX_ATTEMPTS:
            tests = f"Tests still failing after {_MAX_TEST_FIX_ATTEMPTS}+ fix attempts — run stopped at iteration limit."
        else:
            tests = "Tests were not run or did not pass."
        draft_line = _clean_finish_summary(draft)
        if draft_line and not _is_good_finish_summary(draft_line):
            draft_line = ""
        draft_block = f"\n{draft_line}\n" if draft_line else "\n"
        return feedback(files=files, draft=draft_block, tests=tests)

    def _result(
        self,
        *,
        final_answer: str,
        steps: list[AgentStep],
        iterations: int,
        stop_reason: StopReason,
        error: str | None = None,
        verification_report: str | None = None,
    ) -> AgentResult:
        if self._run_id:
            self._close_thought_stream()
        result = AgentResult(
            final_answer=final_answer,
            steps=steps,
            iterations=iterations,
            stop_reason=stop_reason,
            error=error,
            verification_attempts=self._failed_verifications,
            verification_report=verification_report or self._last_verification_report or None,
            metrics=self._build_metrics(steps),
        )
        if stop_reason is StopReason.ERROR:
            self._emit(agent_events.ERROR, {"text": error or "error"})
        elif stop_reason is StopReason.COMPLETED and final_answer and "<tool_call=" not in final_answer:
            streamed = (self._last_streamed or "").strip()
            answer = final_answer.strip()
            already_streamed_same = (
                self._last_stream_channel == "assistant"
                and streamed
                and streamed == answer
            )
            if not already_streamed_same:
                self._emit(agent_events.FINAL, {"text": final_answer})
        self._emit(
            agent_events.STOPPED,
            {"reason": stop_reason.value, "error": error},
        )
        return result

    def _record_step(
        self,
        engine: ContextEngine,
        iteration: int,
        *,
        prompt: str,
        model_output: str,
        reasoning_need: str,
        reasoning_summary: str,
        tool_calls: list[Any] | None = None,
        tool_results: list[Any] | None = None,
    ) -> AgentStep:
        engine.record_turn(
            iteration,
            model_output=model_output,
            tool_results=tool_results,
        )
        self._remember_code_results(engine, tool_results or [], iteration)
        return AgentStep(
            iteration=iteration,
            prompt=prompt,
            model_output=model_output,
            tool_calls=list(tool_calls or []),
            tool_results=list(tool_results or []),
            reasoning_need=reasoning_need,
            reasoning_summary=reasoning_summary or None,
        )

    def _build_metrics(self, steps: list[AgentStep]) -> LoopMetrics:
        names = [call.name for step in steps for call in step.tool_calls]
        by_name: dict[str, int] = {}
        for name in names:
            by_name[name] = by_name.get(name, 0) + 1
        last_prompt = steps[-1].prompt if steps else ""
        epistemic = self._epistemic
        return LoopMetrics(
            iterations=len(steps),
            final_prompt_chars=len(last_prompt),
            tool_call_count=len(names),
            tool_calls_by_name=by_name,
            reasoning_cycles=self._reasoning_model_calls,
            epistemic_calls=by_name.get("ask_epistemic", 0),
            epistemic_subagent_iterations=getattr(epistemic, "total_subagent_steps", 0) if epistemic else 0,
            verification_runs=self._verification_runs,
            verification_failures=self._failed_verifications,
            elapsed_seconds=round(time.monotonic() - self._run_started, 4) if self._run_started else 0.0,
        )

    def _verification_enabled(self) -> bool:
        if self._verification_root is None:
            return False
        try:
            from mango_verification import load_verification_config
        except ImportError:
            return False
        loaded = load_verification_config(self._verification_root, self._verification_config)
        return loaded.has_any_command()

    def _needs_tool(self) -> bool:
        if self._syntax_broken:
            return True
        if self._plan_gate_phase() is not None:
            return True
        if self._verification_enabled() and self._last_verification_ok is not True:
            return True
        if not self._require_tools:
            # Some unit-test / interactive tasks expect immediate filesystem interaction
            # even without `require_tools=True`.
            if not self._acted_once and self._goal_wants_file_io:
                return True
            return False
        if self._research_still_required():
            return True
        if not self._acted_once:
            return True
        if self._task_wants_tests and not self._ran_tests_ok:
            return True
        if self._design_review_still_required():
            return True
        return False

    def _effective_tool_max_tokens(self, names: list[str]) -> int | None:
        """GBNF write_file JSON is escaped Python; the 384 default tail truncates real modules."""
        configured = self._tool_max_tokens
        mutating = any(name in _CODE_MUTATING_TOOLS for name in names)
        if mutating:
            floor = int(self._write_tool_max_tokens or _WRITE_TOOL_MAX_TOKENS)
            if configured is None:
                return floor
            return max(int(configured), floor)
        return configured

    def _action_grammar(self) -> str | None:
        if not self._use_tool_grammar:
            return None
        if self._verification_enabled() and self._last_verification_ok is True:
            return None
        return tool_call_gbnf(self._action_tool_names(), schemas=self._registry.schemas())

    def _action_tool_names(self) -> list[str]:
        names = [
            schema.name
            for schema in self._registry.schemas()
            if schema.name not in self._disabled_tools
        ]
        if self._last_verification_ok is False:
            names = [name for name in names if name in _CODE_MUTATING_TOOLS or name == "run_tests"]
        if self._research_still_required():
            lookup_names = [name for name in names if name in _RESEARCH_TOOLS and name != "web_research"]
            if lookup_names:
                names = lookup_names
        if self._rename_pair and "rename_symbol" in names:
            names = ["rename_symbol", *[name for name in names if name != "rename_symbol"]]
        if self._require_tools and self._task_wants_tests and not self._ran_tests_ok:
            names = [name for name in names if name != "run_terminal_command"]
        if self._tests_still_required() and self._plan_gate_phase() is None:
            names = [name for name in names if name in _CODE_MUTATING_TOOLS or name == "run_tests"]
            missing_tests = not self._discover_test_files()
            if (self._prefer_write_file or missing_tests) and "write_file" in names:
                names = ["write_file", *[name for name in names if name != "write_file"]]
            else:
                names = ["run_tests", *[name for name in names if name != "run_tests"]]
        elif self._design_review_still_required() and "read_file" in names:
            names = ["read_file"]
        elif self._lock_coarsened and self._review_done and "edit_file" in names:
            names = [
                "edit_file",
                *[
                    name
                    for name in names
                    if name in _CODE_MUTATING_TOOLS or name == "read_file"
                ],
            ]
        elif self._prefer_write_file and "write_file" in names:
            names = ["write_file", *[name for name in names if name != "write_file"]]
        phase = self._plan_gate_phase()
        if phase == "declare" and "declare_apis" in names:
            names = [
                "declare_apis",
                *[name for name in names if name == "ask_epistemic" or name in _PLAN_READONLY],
            ]
        elif phase == "epistemic" and "ask_epistemic" in names:
            names = ["ask_epistemic", *[name for name in names if name in _PLAN_READONLY]]
        if (
            self._plan_apis_enabled()
            and self._epistemic_once
            and not self._acted_once
            and "write_file" in names
        ):
            names = ["write_file"]
        if self._inspect_before_edit() and not self._inspected_once:
            inspect_names = [name for name in names if name in _EXPLORE_TOOLS]
            if self._located_once and "read_file" in inspect_names:
                inspect_names = ["read_file", *[name for name in inspect_names if name != "read_file"]]
            elif not self._located_once:
                for preferred in ("search_code", "codebase_lookup"):
                    if preferred in inspect_names:
                        inspect_names = [preferred, *[name for name in inspect_names if name != preferred]]
                        break
            if inspect_names:
                names = inspect_names
        if not names:
            names = [
                schema.name
                for schema in self._registry.schemas()
                if schema.name not in self._disabled_tools
            ]
        if not names:
            names = [schema.name for schema in self._registry.schemas()]
        if self._experiment_exhausted:
            names = [name for name in names if name not in _CODE_MUTATING_TOOLS]
            if not names:
                names = [
                    name
                    for name in ("read_file", "run_tests", "measure")
                    if self._registry.has(name) and name not in self._disabled_tools
                ]
        return names

    def _feedback_failed_tools(self, engine: ContextEngine, tool_results: list[ToolResult]) -> None:
        failed = [result for result in tool_results if not result.success]
        if not failed:
            return
        if all(
            result.metadata.get("blocked") and "3 reverts" in str(result.error or "")
            for result in failed
        ):
            engine.set_verification_feedback(feedback("experiment.exhausted"))
            return
        lines = [f"{result.tool_name} failed: {result.error or 'failed'}" for result in failed]
        extra_snippets: list[str] = []
        for result in failed:
            err = str(result.error or "failed")
            call = getattr(result, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            path = arguments.get("path") if isinstance(arguments, dict) else None
            if (
                path
                and "old_string not found" not in err.lower()
                and not _looks_like_test_path(str(path))
            ):
                self._pending_impl_files.append(self._abs_impl_path(str(path)))
            if (
                result.tool_name in {"edit_file", "edit_symbol"}
                and isinstance(arguments, dict)
            ):
                if path and result.tool_name == "edit_file":
                    key = self._abs_impl_path(str(path))
                    self._edit_fail_counts[key] = self._edit_fail_counts.get(key, 0) + 1
                    if self._edit_fail_counts[key] >= 2:
                        self._prefer_write_file = True
                locate = self._locate_failed_edit(arguments, err, path)
                extra_snippets.extend(locate)
        lines.append(feedback("retry"))
        if self._prefer_write_file:
            lines.append(feedback("write_file"))
        if extra_snippets:
            lines.append("\n".join(extra_snippets))
        engine.set_verification_feedback("\n".join(lines))

    def _grounded_edits_enabled(self) -> bool:
        if not self._require_tools or self._verification_root is None:
            return False
        if self._greenfield_run:
            return False
        if self._impl_python_files():
            return True
        if self._discover_test_files():
            return True
        if _GOAL_IMPLIES_EDIT.search(self._task or "") and self._pending_goal_files:
            return True
        return False

    def _inspect_before_edit(self) -> bool:
        if not self._require_tools:
            return False
        if "write_file" in self._disabled_tools:
            return True
        return self._grounded_edits_enabled()

    def _goal_mentions_test_file(self, path: str) -> bool:
        name = Path(normalize_tool_path(path)).name.lower()
        blob = (self._task or "").lower()
        if name and name in blob:
            return True
        return any(
            Path(normalize_tool_path(rel)).name.lower() == name
            for rel in self._pending_goal_files
            if _looks_like_test_path(rel)
        )

    def _grounding_block_reason(self, call: ToolCall) -> str | None:
        if call.name not in _CODE_MUTATING_TOOLS:
            return None
        if not self._grounded_edits_enabled():
            return None
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        path = arguments.get("path")
        if not isinstance(path, str) or not path.strip():
            return None
        if _looks_like_test_path(path) and not self._goal_mentions_test_file(path):
            if not self._impl_mutated_once:
                return feedback("blocked_edit_test_first")
        abs_path = self._abs_impl_path(path)
        file_exists = Path(abs_path).is_file()
        if call.name == "edit_file" and file_exists and abs_path not in self._files_read:
            return feedback("blocked_edit_not_read", path=self._display_path(abs_path))
        if call.name == "write_file" and file_exists and abs_path not in self._files_read:
            return feedback("blocked_edit_not_read", path=self._display_path(abs_path))
        return None

    def _note_read_files(self, tool_results: list[ToolResult]) -> None:
        for result in tool_results:
            if not result.success or result.tool_name != "read_file":
                continue
            output = result.output if isinstance(result.output, dict) else {}
            path = str(output.get("absolute_path") or output.get("path") or "")
            call = result.call
            if not path and call is not None and isinstance(call.arguments, dict):
                path = str(call.arguments.get("path") or "")
            if path:
                self._files_read.add(self._abs_impl_path(path))

    def _note_impl_mutations(self, tool_results: list[ToolResult]) -> None:
        for result in tool_results:
            if not result.success or result.tool_name not in _CODE_MUTATING_TOOLS:
                continue
            output = result.output if isinstance(result.output, dict) else {}
            raw = str(output.get("path") or output.get("absolute_path") or "")
            call = getattr(result, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            if not raw and isinstance(arguments, dict):
                raw = str(arguments.get("path") or "")
            if raw and not _looks_like_test_path(raw):
                self._impl_mutated_once = True

    def _reject_fuzzy_edits(self, tool_results: list[ToolResult]) -> list[ToolResult]:
        if not self._grounded_edits_enabled():
            return tool_results
        rewritten: list[ToolResult] = []
        for result in tool_results:
            if (
                result.success
                and result.tool_name == "edit_file"
                and isinstance(result.output, dict)
                and result.output.get("fuzzy")
            ):
                call = getattr(result, "call", None)
                arguments = getattr(call, "arguments", None) if call is not None else None
                path = ""
                if isinstance(arguments, dict):
                    path = str(arguments.get("path") or "")
                display = self._display_path(self._abs_impl_path(path)) if path else "the file"
                rewritten.append(
                    ToolResult(
                        success=False,
                        tool_name=result.tool_name,
                        error=feedback("blocked_edit_fuzzy", path=display),
                        call=call,
                        metadata={"blocked": True},
                    )
                )
                continue
            rewritten.append(result)
        return rewritten

    def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        phase = self._plan_gate_phase()
        tool_ctx = {**self._tool_context(), "_cancelled": self._cancelled}
        if phase is not None:
            allowed_names = set(_PLAN_ALLOWED)
            allowed = [call for call in tool_calls if call.name in allowed_names]
            blocked = [call for call in tool_calls if call.name not in allowed_names]
            results: list[ToolResult] = []
            if allowed:
                results.extend(run_tool_calls(allowed, self._registry, context=tool_ctx))
            if blocked:
                self._trace(
                    f"iter {self._current_iteration} blocked before {phase}="
                    f"{[call.name for call in blocked]}"
                )
                if phase == "declare":
                    err = feedback("blocked_declare")
                else:
                    libs = ", ".join(self._plan_coverage_libraries() or self._impl_declared_libraries()) or "the declared libraries"
                    err = feedback("blocked_epistemic", libs=libs)
                results.extend(
                    ToolResult(success=False, tool_name=call.name, error=err, call=call, metadata={"blocked": True})
                    for call in blocked
                )
            return results
        if self._experiment_exhausted:
            allowed = [call for call in tool_calls if call.name not in _CODE_MUTATING_TOOLS]
            blocked = [call for call in tool_calls if call.name in _CODE_MUTATING_TOOLS]
            results: list[ToolResult] = []
            if allowed:
                results.extend(run_tool_calls(allowed, self._registry, context=tool_ctx))
            if blocked:
                err = feedback("experiment.exhausted")
                results.extend(
                    ToolResult(
                        success=False,
                        tool_name=call.name,
                        error=err,
                        call=call,
                        metadata={"blocked": True},
                    )
                    for call in blocked
                )
            return results
        if self._inspect_before_edit() and not self._inspected_once:
            allowed = [call for call in tool_calls if call.name not in _CODE_MUTATING_TOOLS]
            blocked = [call for call in tool_calls if call.name in _CODE_MUTATING_TOOLS]
            results: list[ToolResult] = []
            if allowed:
                results.extend(run_tool_calls(allowed, self._registry, context=tool_ctx))
            if blocked:
                self._trace(
                    f"iter {self._current_iteration} blocked premature edit="
                    f"{[call.name for call in blocked]}"
                )
                results.extend(
                    ToolResult(
                        success=False,
                        tool_name=call.name,
                        error=(
                            feedback("blocked_edit_read")
                            if self._located_once
                            else feedback("blocked_edit_search")
                        ),
                        call=call,
                        metadata={"blocked": True},
                    )
                    for call in blocked
                )
            return results
        grounded_allowed: list[ToolCall] = []
        grounded_blocked: list[ToolResult] = []
        for call in tool_calls:
            reason = self._grounding_block_reason(call)
            if reason:
                grounded_blocked.append(
                    ToolResult(
                        success=False,
                        tool_name=call.name,
                        error=reason,
                        call=call,
                        metadata={"blocked": True},
                    )
                )
            else:
                grounded_allowed.append(call)
        if grounded_blocked and not grounded_allowed:
            return grounded_blocked
        results = list(grounded_blocked)
        if grounded_allowed:
            results.extend(run_tool_calls(grounded_allowed, self._registry, context=tool_ctx))
        return results

    def _inspect_result_is_useful(self, result: ToolResult) -> bool:
        if not result.success:
            return False
        if result.tool_name == "read_file":
            output = result.output if isinstance(result.output, dict) else {}
            path = str(output.get("path") or output.get("absolute_path") or "")
            call = result.call
            if not path and call is not None and isinstance(call.arguments, dict):
                path = str(call.arguments.get("path") or "")
            return bool(path) and not _looks_like_test_path(path)
        if result.tool_name == "search_code":
            return self._search_found_impl(result)
        if result.tool_name == "codebase_lookup":
            return self._codebase_lookup_found_impl(result)
        return False

    def _search_found_impl(self, result: ToolResult) -> bool:
        if not result.success or result.tool_name != "search_code":
            return False
        if not isinstance(result.output, dict):
            return False
        matches = result.output.get("matches") or []
        return any(
            isinstance(item, dict)
            and not _looks_like_test_path(str(item.get("path") or ""))
            for item in matches
        )

    def _codebase_lookup_found_impl(self, result: ToolResult) -> bool:
        if not result.success or result.tool_name != "codebase_lookup":
            return False
        if not isinstance(result.output, dict):
            return False
        files = result.output.get("files") or []
        if isinstance(files, list) and any(isinstance(item, dict) and item.get("path") for item in files):
            return any(
                isinstance(item, dict)
                and item.get("path")
                and not _looks_like_test_path(str(item.get("path")))
                for item in files
            )
        definitions = result.output.get("definitions") or []
        if isinstance(definitions, list) and any(isinstance(item, dict) and item.get("path") for item in definitions):
            return any(
                isinstance(item, dict)
                and item.get("path")
                and not _looks_like_test_path(str(item.get("path")))
                for item in definitions
            )
        return False

    def _locate_failed_edit(
        self,
        arguments: dict[str, Any],
        err: str,
        path: str | None,
    ) -> list[str]:
        notes: list[str] = []
        if path and _looks_like_test_path(str(path)):
            notes.append(feedback("test_file", path=path))
        symbol = _symbol_from_edit_args(arguments)
        missing = "old_string not found" in err.lower() or "file not found" in err.lower()
        if not symbol and not missing:
            return notes
        if symbol:
            hits = self._search_impl_hits(rf"\b{re.escape(symbol)}\b")
        else:
            query = str(arguments.get("old_string") or arguments.get("new_string") or "")[:60]
            if not query.strip():
                return notes
            hits = self._search_impl_hits(re.escape(query))
        impl_hits = [
            hit for hit in hits if not _looks_like_test_path(str(hit.get("path") or ""))
        ]
        if impl_hits:
            self._located_once = True
        chosen = impl_hits or hits
        if chosen:
            rendered = []
            for hit in chosen[:8]:
                hit_path = self._display_path(str(hit.get("path") or ""))
                line_no = hit.get("line")
                text = str(hit.get("text") or "").strip()[:160]
                rendered.append(f"- {hit_path}:{line_no}: {text}")
                abs_hit = str(hit.get("path") or "")
                if abs_hit and not _looks_like_test_path(abs_hit):
                    self._pending_impl_files.append(self._abs_impl_path(abs_hit))
            notes.append(feedback("matches", hits="\n".join(rendered)))
        elif path and missing:
            abs_path = self._abs_impl_path(str(path))
            snippet = _snippet_around_symbol(abs_path, symbol) if symbol else ""
            if snippet:
                notes.append(
                    feedback(
                        "snippet",
                        symbol=symbol,
                        path=self._display_path(abs_path),
                        snippet=snippet,
                    )
                )
        return notes

    def _search_impl_hits(self, pattern: str, *, max_results: int = 24) -> list[dict[str, Any]]:
        from mango_tools.implementations.search_code import search_code

        try:
            output = search_code(
                pattern,
                ".",
                include_glob="**/*.py",
                max_results=max_results,
                _context=self._tool_context(),
            )
        except Exception:
            return []
        matches = output.get("matches") if isinstance(output, dict) else None
        if not isinstance(matches, list):
            return []
        return [item for item in matches if isinstance(item, dict)]

    def _handle_run_tests_results(
        self,
        results: list[ToolResult],
        engine: ContextEngine,
    ) -> None:
        """Apply test outcomes and nudge the model to keep fixing until tests pass."""
        for result in results:
            if result.tool_name != "run_tests" or not isinstance(result.output, dict):
                continue
            if bool(result.output.get("ok")):
                if self._concurrency_tests_missing():
                    self._ran_tests_ok = False
                    self._stress_nudges += 1
                    if self._stress_nudges <= _MAX_STRESS_NUDGES:
                        engine.set_verification_feedback(feedback("stress"))
                        continue
                if not self._runtime_smoke_passes(engine):
                    continue
                self._ran_tests_ok = True
                self._run_tests_failures = 0
                self._runtime_smoke_failures = 0
                if self._design_review_still_required():
                    engine.set_verification_feedback(
                        review_message(coarsened=self._lock_coarsened)
                    )
                continue
            targets = result.output.get("targets") or []
            if not targets:
                engine.set_verification_feedback(feedback("no_tests"))
                continue
            self._run_tests_failures += 1
            timed_out = bool(result.output.get("timed_out"))
            detail = str(result.output.get("stderr") or result.output.get("stdout") or "").strip()
            hint = "timed out" if timed_out else "failed"
            extra = ""
            if self._impl_looks_concurrent() and not self._tests_cover_concurrency():
                extra = feedback("concurrent_hint")
            remaining = _MAX_TEST_FIX_ATTEMPTS - self._run_tests_failures
            detail_block = f"\n{detail[:800]}" if detail else ""
            if self._run_tests_failures >= _MAX_TEST_FIX_ATTEMPTS:
                engine.set_verification_feedback(
                    feedback(
                        "failed_persistent",
                        hint=hint,
                        attempts=_MAX_TEST_FIX_ATTEMPTS,
                        detail=detail_block,
                    )
                )
                continue
            snap = self._capture_impl_snapshot(engine)
            snap_block = f"\nCurrent implementation:\n{snap}" if snap else ""
            engine.set_verification_feedback(
                feedback(
                    "failed",
                    hint=hint,
                    attempt=self._run_tests_failures,
                    attempts=_MAX_TEST_FIX_ATTEMPTS,
                    remaining=remaining,
                    extra=extra,
                    detail=detail_block + snap_block,
                )
            )

    def _runtime_smoke_passes(self, engine: ContextEngine) -> bool:
        """Pytest green is not enough — smoke-run __main__ scripts for real crashes."""
        from mango_tools.implementations.runtime_smoke import run_runtime_smoke

        prefer = [path for path in self._impl_python_files() if not _looks_like_test_path(path)]
        ctx = {**self._tool_context(), "prefer_scripts": prefer[:8]}
        smoke = run_runtime_smoke(_context=ctx)
        if smoke.get("skipped"):
            return True
        if bool(smoke.get("ok")):
            return True
        self._ran_tests_ok = False
        self._runtime_smoke_failures += 1
        failed = str(smoke.get("failed_script") or "entry script")
        detail = str(smoke.get("detail") or smoke.get("stderr") or smoke.get("stdout") or "").strip()
        display = self._display_path(failed) if failed else "entry script"
        engine.set_verification_feedback(
            feedback(
                "runtime_failed",
                script=display,
                detail=f"\n{detail[:900]}" if detail else "",
            )
        )
        return False

    def _tests_still_required(self) -> bool:
        return bool(
            self._require_tools
            and self._task_wants_tests
            and not self._ran_tests_ok
            and not self._syntax_broken
            and self._acted_once
        )

    def _design_review_still_required(self) -> bool:
        return bool(
            self._require_tools
            and self._review_needed
            and not self._review_done
            and self._acted_once
            and not self._syntax_broken
        )

    def _design_review_blocked(self) -> bool:
        return self._design_review_still_required() or self._review_hold > 0

    def _arm_design_review_state(
        self,
        tool_results: list[ToolResult],
        snapshots: dict[str, str],
    ) -> None:
        for abs_path in self._mutated_python_paths(tool_results):
            if _looks_like_test_path(abs_path):
                continue
            old = snapshots.get(abs_path, "")
            try:
                new = Path(abs_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            concurrent = bool(
                _CONCURRENCY_IMPL.search(old or "") or _CONCURRENCY_IMPL.search(new or "")
            )
            coarsened = lock_coarsened(old, new)
            if not concurrent and not coarsened:
                continue
            self._review_paths.add(abs_path)
            self._review_needed = True
            self._review_done = False
            self._review_hold = 0
            if coarsened:
                self._lock_coarsened = True

    def _note_review_reads(self, engine: ContextEngine, tool_results: list[ToolResult]) -> None:
        if not self._review_needed or self._review_done:
            return
        for result in tool_results:
            if not result.success or result.tool_name != "read_file":
                continue
            output = result.output if isinstance(result.output, dict) else {}
            call = getattr(result, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            raw = str(output.get("path") or output.get("absolute_path") or "")
            if not raw and isinstance(arguments, dict):
                raw = str(arguments.get("path") or "")
            if not raw:
                continue
            abs_path = self._abs_impl_path(raw)
            if _looks_like_test_path(abs_path):
                continue
            if self._review_paths and abs_path not in self._review_paths:
                # Accept a read of any mutated impl; Windows path variants may differ.
                review_names = {Path(path).name for path in self._review_paths}
                if Path(abs_path).name not in review_names:
                    continue
            self._review_done = True
            self._review_hold = 1
            if self._lock_coarsened:
                engine.set_verification_feedback(coarsen_after_read_message())
            return

    def _run_workspace_tests(self, iteration: int) -> list[ToolResult]:
        self._emit(
            agent_events.TOOL,
            {
                "id": f"tool-run-tests-{self._run_id}-{iteration}",
                "name": "run_tests",
                "title": "Running tests…",
                "streaming": True,
                "console": True,
            },
        )
        from mango_tools.implementations.run_tests import run_tests

        output = run_tests(
            _context=self._tool_context(),
            test_paths=self._candidate_test_paths() or None,
        )
        call = ToolCall(name="run_tests", arguments={}, raw="", start=0, end=0)
        return [
            ToolResult(
                success=True,
                tool_name="run_tests",
                output=output,
                call=call,
            )
        ]

    def _auto_run_tests_if_needed(
        self,
        tool_results: list[ToolResult],
        iteration: int,
    ) -> list[ToolResult]:
        if not self._require_tools:
            return []
        if any(result.tool_name == "run_tests" for result in tool_results):
            return []
        mutated = bool(self._mutated_python_paths(tool_results)) or any(
            result.success and result.tool_name in _CODE_MUTATING_TOOLS for result in tool_results
        )
        if not mutated:
            return []
        if not self._discover_test_files():
            return []
        if self._experiments_enabled():
            return self._run_workspace_tests(iteration)
        if not self._task_wants_tests or self._ran_tests_ok:
            return []
        return self._run_workspace_tests(iteration)

    def _experiments_enabled(self) -> bool:
        return bool(self._require_tools and "write_file" not in self._disabled_tools)

    def _tests_ok_from_results(self, results: list[ToolResult]) -> bool | None:
        found: bool | None = None
        for result in results:
            if result.tool_name != "run_tests" or not isinstance(result.output, dict):
                continue
            found = bool(result.output.get("ok"))
        return found

    def _measure_from_results(self, results: list[ToolResult]) -> dict[str, Any] | None:
        for result in reversed(results):
            if result.tool_name != "measure" or not result.success:
                continue
            if isinstance(result.output, dict):
                return result.output
        return None

    def _fallback_measure_command(self) -> str | None:
        if not self._discover_test_files():
            return None
        return f"{sys.executable} -m pytest -q"

    def _run_measure(self, command: str, *, repeats: int = 5) -> dict[str, Any] | None:
        from mango_tools.implementations.measure import measure as run_measure

        if not command or self._cancelled():
            return None
        try:
            return run_measure(
                command,
                repeats=repeats,
                _context={**self._tool_context(), "_cancelled": self._cancelled},
            )
        except Exception:
            return None

    def _maybe_capture_perf_baseline(self) -> None:
        if not self._experiments_enabled() or not goal_wants_perf(self._task):
            return
        if self._experiment_baseline is not None:
            return
        command = self._experiment_command or self._fallback_measure_command()
        if not command:
            return
        measured = self._run_measure(command)
        if not measured or not measured.get("ok") or measured.get("median_ms") is None:
            return
        self._experiment_command = str(measured.get("command") or command)
        self._experiment_baseline = {
            "command": self._experiment_command,
            "median_ms": float(measured["median_ms"]),
        }

    def _collect_perf_pair(
        self,
        tool_results: list[ToolResult],
        *,
        tests_ok: bool | None,
    ) -> tuple[float | None, float | None, bool]:
        """Return (before_ms, after_ms, command_changed)."""
        if not goal_wants_perf(self._task) or tests_ok is False:
            return None, None, False
        model_measure = self._measure_from_results(tool_results)
        if model_measure and model_measure.get("command"):
            self._experiment_command = str(model_measure["command"])
        command = self._experiment_command or self._fallback_measure_command()
        baseline = self._experiment_baseline
        if baseline and command and str(baseline.get("command") or "") != command:
            after = None
            if model_measure and model_measure.get("median_ms") is not None:
                after = float(model_measure["median_ms"])
            return (
                float(baseline["median_ms"]) if baseline.get("median_ms") is not None else None,
                after,
                True,
            )
        after: float | None = None
        if model_measure and model_measure.get("median_ms") is not None:
            after = float(model_measure["median_ms"])
        elif command:
            measured = self._run_measure(command)
            if measured and measured.get("ok") and measured.get("median_ms") is not None:
                after = float(measured["median_ms"])
                self._experiment_command = str(measured.get("command") or command)
        before = None
        if baseline and baseline.get("median_ms") is not None:
            before = float(baseline["median_ms"])
        return before, after, False

    def _conclude_experiment(
        self,
        engine: ContextEngine,
        snapshots: dict[str, str],
        tool_results: list[ToolResult],
        *,
        syntax_bad: bool,
        iteration: int,
    ) -> bool:
        if not self._experiments_enabled():
            return False
        mutated = any(
            result.success and result.tool_name in _CODE_MUTATING_TOOLS for result in tool_results
        )
        if not mutated:
            model_measure = self._measure_from_results(tool_results)
            if model_measure and model_measure.get("ok") and model_measure.get("median_ms") is not None:
                command = str(model_measure.get("command") or self._experiment_command or "")
                if command:
                    self._experiment_command = command
                if self._experiment_baseline is None:
                    self._experiment_baseline = {
                        "command": self._experiment_command,
                        "median_ms": float(model_measure["median_ms"]),
                    }
            return False
        tests_ok = self._tests_ok_from_results(tool_results)
        before, after, command_changed = (None, None, False)
        if not syntax_bad:
            before, after, command_changed = self._collect_perf_pair(
                tool_results, tests_ok=tests_ok
            )
        claim = claimed_speedup_pct(f"{self._last_hypothesis}\n{self._task}")
        verdict = decide_experiment(
            syntax_ok=not syntax_bad,
            tests_ok=tests_ok,
            before_ms=before,
            after_ms=after,
            claimed_speedup_pct=claim,
            hypothesis=self._last_hypothesis,
            command_changed=command_changed,
        )
        reverted = False
        if verdict.decision == "revert":
            restored = self._restore_experiment_files(snapshots)
            reverted = True
            if restored:
                self._experiment_reverts += 1
                if self._experiment_reverts >= MAX_REVERTS:
                    self._experiment_exhausted = True
                    self._experiment_locked_paths.update(snapshots.keys())
            if tests_ok is False:
                self._ran_tests_ok = False
            self._trace(f"iter {iteration} experiment revert {verdict.reason}")
        elif verdict.reason != "command_changed" and after is not None and self._experiment_command:
            self._experiment_baseline = {
                "command": self._experiment_command,
                "median_ms": after,
            }
        self._emit_experiment(verdict)
        self._feedback_experiment(engine, verdict)
        return reverted

    def _restore_experiment_files(self, snapshots: dict[str, str]) -> list[str]:
        restored: list[str] = []
        for abs_path, previous in snapshots.items():
            if not previous.strip():
                continue
            path = Path(abs_path)
            try:
                current = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            except OSError:
                current = ""
            restore_snapshots({abs_path: previous})
            restored.append(abs_path)
            added, removed = agent_events.line_stats(current, previous)
            self._emit(
                agent_events.FILE,
                {
                    "action": "edited",
                    "path": self._display_path(abs_path),
                    "absolute_path": abs_path,
                    "added": added,
                    "removed": removed,
                    "diff": agent_events.unified_diff(abs_path, current, previous),
                },
            )
        return restored

    def _emit_experiment(self, verdict: Any) -> None:
        self._emit(
            agent_events.EXPERIMENT,
            {
                "hypothesis": verdict.hypothesis,
                "before": verdict.before,
                "after": verdict.after,
                "unit": verdict.unit,
                "decision": verdict.decision,
                "delta_pct": verdict.delta_pct,
                "reason": verdict.reason,
            },
        )

    def _feedback_experiment(self, engine: ContextEngine, verdict: Any) -> None:
        before = "n/a" if verdict.before is None else str(verdict.before)
        after = "n/a" if verdict.after is None else str(verdict.after)
        delta = "n/a" if verdict.delta_pct is None else f"{verdict.delta_pct:+.1f}%"
        unit = verdict.unit or "ms"
        if verdict.decision == "revert":
            text = feedback(
                "experiment.reverted",
                reason=str(verdict.reason).replace("_", " "),
                before=before,
                after=after,
                unit=unit,
                delta=delta,
            )
            if self._experiment_exhausted:
                text = f"{text}\n{feedback('experiment.exhausted')}"
            engine.set_verification_feedback(text)
            return
        if verdict.reason == "unsupported":
            claim = claimed_speedup_pct(f"{verdict.hypothesis}\n{self._task}")
            engine.set_verification_feedback(
                feedback(
                    "experiment.unsupported",
                    claim=f"{claim:g}%" if claim is not None else "the claimed gain",
                    delta=delta,
                )
            )
            return
        if verdict.reason == "command_changed":
            engine.set_verification_feedback(feedback("experiment.command_changed"))
            return
        if verdict.before is not None and verdict.after is not None:
            engine.set_verification_feedback(
                feedback(
                    "experiment.kept",
                    before=before,
                    after=after,
                    unit=unit,
                    delta=delta,
                )
            )

    def _concurrency_tests_missing(self) -> bool:
        return self._impl_looks_concurrent() and not self._tests_cover_concurrency()

    def _impl_looks_concurrent(self) -> bool:
        blob = self._read_py_blob(self._impl_python_files())
        return bool(blob and _CONCURRENCY_IMPL.search(blob))

    def _tests_cover_concurrency(self) -> bool:
        blob = self._read_py_blob(self._discover_test_files())
        return bool(blob and _CONCURRENCY_TEST.search(blob))

    def _read_py_blob(self, paths: list[str], *, limit: int = 16) -> str:
        chunks: list[str] = []
        for path in paths[:limit]:
            try:
                chunks.append(Path(path).read_text(encoding="utf-8", errors="replace")[:80_000])
            except OSError:
                continue
        return "\n".join(chunks)

    def _note_repo_impact(self, engine: ContextEngine, tool_results: list[ToolResult]) -> None:
        if self._codeintel is None:
            return
        paths = [
            path
            for path in self._mutated_python_paths(tool_results)
            if not _looks_like_test_path(path)
        ]
        if not paths:
            return
        try:
            self._codeintel.refresh()
        except Exception:
            return
        bits: list[str] = []
        for abs_path in paths[:4]:
            rel = self._display_path(abs_path)
            try:
                data = self._codeintel.query.impact(path=rel)
            except Exception:
                continue
            deps = list(data.get("dependent_files") or [])
            tests = list(data.get("test_files") or [])
            if not deps and not tests:
                continue
            parts: list[str] = []
            if deps:
                parts.append("used by " + ", ".join(deps[:6]))
            if tests:
                parts.append("tests: " + ", ".join(tests[:4]))
            bits.append(f"{rel}: " + "; ".join(parts))
        if not bits:
            return
        engine.set_verification_feedback(feedback(bits="\n".join(bits)))

    def _clear_edit_failures(self, tool_results: list[ToolResult]) -> None:
        for result in tool_results:
            if not result.success or result.tool_name not in _CODE_MUTATING_TOOLS:
                continue
            output = result.output if isinstance(result.output, dict) else {}
            raw = str(output.get("path") or output.get("absolute_path") or "")
            call = getattr(result, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            if not raw and isinstance(arguments, dict):
                raw = str(arguments.get("path") or "")
            if raw:
                self._edit_fail_counts.pop(self._abs_impl_path(raw), None)

    def _fallback_failed_edits(self, tool_results: list[ToolResult]) -> list[ToolResult]:
        rewritten: list[ToolResult] = []
        for result in tool_results:
            if result.metadata.get("blocked") or "BLOCKED" in str(result.error or ""):
                rewritten.append(result)
                continue
            if result.success or result.tool_name != "edit_file":
                rewritten.append(result)
                continue
            call = getattr(result, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            if not isinstance(arguments, dict):
                rewritten.append(result)
                continue
            path = arguments.get("path")
            new_string = arguments.get("new_string")
            if not isinstance(path, str) or not isinstance(new_string, str):
                rewritten.append(result)
                continue
            abs_path = self._abs_impl_path(path)
            existing = ""
            try:
                if Path(abs_path).is_file():
                    existing = Path(abs_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                existing = ""
            if not _should_write_file_fallback(new_string, existing):
                rewritten.append(result)
                continue
            from mango_tools.implementations.write_file import write_file

            try:
                output = write_file(path, new_string, _context=self._tool_context())
            except Exception:
                rewritten.append(result)
                continue
            self._prefer_write_file = True
            payload = dict(output)
            payload["match"] = "write_file_fallback"
            payload["fallback_from"] = "edit_file"
            rewritten.append(
                ToolResult(
                    success=True,
                    tool_name="write_file",
                    output=payload,
                    call=call,
                )
            )
        return rewritten

    def _maybe_verify(
        self,
        engine: ContextEngine,
        iteration: int,
        tool_results: list[ToolResult],
    ) -> Any | None:
        if self._syntax_broken:
            return None
        if not self._verification_enabled():
            return None
        mutated = any(
            result.success and result.tool_name in _CODE_MUTATING_TOOLS for result in tool_results
        )
        ran_tests = any(result.success and result.tool_name == "run_tests" for result in tool_results)
        if not mutated and not ran_tests:
            self._queue_failed_mutation_paths(tool_results)
            return None
        if self._timed_out():
            return None
        return self._execute_verification(engine, iteration)

    def _queue_failed_mutation_paths(self, tool_results: list[ToolResult]) -> None:
        noop = False
        for result in tool_results:
            if result.success or result.tool_name not in _CODE_MUTATING_TOOLS:
                continue
            call = getattr(result, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            path = arguments.get("path") if isinstance(arguments, dict) else None
            if path and path not in {".", ""}:
                self._pending_impl_files.append(self._abs_impl_path(str(path)))
            if "file unchanged" in str(getattr(result, "error", "") or "").lower():
                noop = True
        for rel in self._ledger.impl_paths(failing_only=True):
            self._pending_impl_files.append(self._abs_impl_path(rel))
        if noop and self._context is not None:
            snippet = self._capture_impl_snapshot(self._context)
            self._context.state.last_noop_snippet = snippet
            if snippet:
                self._context.state.verification_current_source = snippet

    def _execute_verification(self, engine: ContextEngine, iteration: int) -> Any | None:
        if not self._verification_enabled():
            return None
        from mango_verification import run_verification

        result = run_verification(self._verification_root, self._verification_config)
        self._verification_runs += 1
        if result.success:
            self._last_verification_ok = True
        else:
            self._failed_verifications += 1
            self._last_verification_ok = False
            if self._thinking.verify_strength >= 3:
                self._need_fix_cot = True
        report = self._ingest_verification(engine, result)
        self._last_verification_report = report
        engine.set_verification_feedback(report)
        engine.note_raw_result(
            iteration,
            "verification",
            result.success,
            report,
            error=None if result.success else report,
        )
        if engine.state.previous_actions:
            last = engine.state.previous_actions[-1]
            status = "ok" if result.success else "error"
            last.summary = f"{last.summary}; verification ({status})"
        self._emit(
            agent_events.VERIFICATION,
            {"ok": bool(result.success), "report": report},
        )
        return result

    def _ingest_verification(self, engine: ContextEngine, result: Any) -> str:
        failed_names = list((result.test_summary.failed_names if result.test_summary else []) or [])
        errors = list((result.test_summary.errors if result.test_summary else []) or [])
        mappings = map_failed_tests(failed_names, codeintel=self._codeintel, errors=errors)
        report = self._ledger.ingest(
            result,
            mappings,
            attempt=self._verification_runs,
            max_attempts=self._limits.max_fix_attempts,
        )
        failing_tests = self._ledger.still_failing_names()
        failing_paths = self._ledger.impl_paths(failing_only=True)
        failing_symbols = self._ledger.impl_symbols(failing_only=True)
        engine.state.verification_failed_tests = failing_tests
        engine.state.verification_impl_paths = failing_paths
        engine.state.verification_impl_symbols = failing_symbols
        engine.state.allow_multi_edit = (not result.success) and (
            len(failing_tests) >= 2 or len(failing_paths) >= 2 or len(failing_symbols) >= 2
        )
        summary = result.test_summary
        engine.state.verification_collection_error = bool(
            getattr(summary, "collection_errors", None)
        )
        missing = None
        try:
            from mango_verification.parsers import parse_missing_import

            blob = "\n".join(
                [
                    str(getattr(result, "test_output", "") or ""),
                    report,
                    *list((summary.errors if summary else []) or []),
                ]
            )
            missing = parse_missing_import(blob)
        except Exception:
            missing = None
        if missing:
            old_name = self._rename_pair[0] if self._rename_pair else None
            if old_name and missing[0] == old_name:
                engine.state.verification_missing_symbol = None
                engine.state.verification_missing_module = None
                old, new = self._rename_pair
                engine.state.verification_next_edit = (
                    f'Call rename_symbol with {{"old_name": "{old}", "new_name": "{new}", "path": "."}}'
                )
                report = report.replace(
                    f"Define missing symbol {old}",
                    f"Rename {old} to {new} with rename_symbol; do not redefine {old}",
                )
            else:
                engine.state.verification_missing_symbol = missing[0]
                engine.state.verification_missing_module = missing[1] or None
        else:
            engine.state.verification_missing_symbol = None
            engine.state.verification_missing_module = None
        if not (self._rename_pair and missing and missing[0] == self._rename_pair[0]):
            engine.state.verification_next_edit = self._ledger.next_edit_hint()
        if not result.success and engine.state.verification_next_edit:
            report += f"\nNext best edit: {engine.state.verification_next_edit}"
        for rel in failing_paths:
            abs_path = self._abs_impl_path(rel)
            engine.state.note_file(abs_path)
            self._pending_impl_files.append(abs_path)
        if result.success:
            engine.state.verification_current_source = ""
            engine.state.last_noop_snippet = ""
            self._pending_symbol_lookups = []
            self._pending_impl_files = []
        else:
            self._pending_symbol_lookups = list(failing_symbols)
            engine.state.verification_current_source = self._capture_impl_snapshot(engine)
            engine.state.last_noop_snippet = ""
        return report

    def _run_pending_lookups(self, engine: ContextEngine, iteration: int) -> None:
        files = [rel for rel in self._pending_goal_files if rel]
        self._pending_goal_files = []
        if not self._ingested_workspace_tests:
            self._ingested_workspace_tests = True
            files.extend(self._discover_test_files())
        files.extend(self._pending_impl_files)
        self._pending_impl_files = []
        seen: set[str] = set()
        for rel in files:
            abs_path = self._abs_impl_path(rel)
            if abs_path in seen:
                continue
            seen.add(abs_path)
            file_path = Path(abs_path)
            if not file_path.is_file():
                continue
            engine.state.note_file(abs_path)
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            engine.remember_file(abs_path, source, iteration=iteration)

        symbols = [sym for sym in self._pending_symbol_lookups if sym]
        self._pending_symbol_lookups = []
        if not symbols or self._codeintel is None:
            return
        for symbol in symbols:
            data = self._codeintel.lookup(symbol)
            compact = _compact_lookup(data)
            engine.note_raw_result(iteration, "codebase_lookup", True, compact)
            for hit in list(data.get("definitions") or []) + list(data.get("files") or []):
                path = hit.get("path") if isinstance(hit, dict) else getattr(hit, "path", None)
                if path:
                    engine.state.note_file(self._abs_impl_path(str(path)))
            if engine.state.previous_actions:
                last = engine.state.previous_actions[-1]
                extra = f"codebase_lookup:{symbol}"
                if extra not in last.summary:
                    last.summary = f"{last.summary}; {extra}"
            else:
                engine.state.record_action(iteration, f"codebase_lookup:{symbol}")

    def _remember_code_results(
        self,
        engine: ContextEngine,
        tool_results: list[Any],
        iteration: int,
    ) -> None:
        mutated = False
        paths: list[str] = []
        for result in tool_results:
            name = getattr(result, "tool_name", "")
            success = bool(getattr(result, "success", False))
            if not success or name not in {
                "read_file",
                "write_file",
                "edit_file",
                "edit_symbol",
                "rename_symbol",
                "search_code",
            }:
                continue
            output = getattr(result, "output", None)
            found_paths: list[str] = []
            if name == "search_code" and isinstance(output, dict):
                for item in output.get("matches") or []:
                    if not isinstance(item, dict) or not item.get("path"):
                        continue
                    match_path = str(item["path"])
                    if _looks_like_test_path(match_path):
                        continue
                    found_paths.append(match_path)
                    if len(found_paths) >= 2:
                        break
            elif isinstance(output, dict):
                if output.get("path"):
                    found_paths.append(str(output["path"]))
                for item in output.get("files") or []:
                    if isinstance(item, dict) and item.get("path"):
                        found_paths.append(str(item["path"]))
            if not found_paths and name != "search_code":
                call = getattr(result, "call", None)
                arguments = getattr(call, "arguments", None) if call is not None else None
                if isinstance(arguments, dict) and arguments.get("path"):
                    found_paths.append(str(arguments["path"]))
            paths.extend(found_paths)
            if name in _CODE_MUTATING_TOOLS:
                mutated = True
        if mutated and self._codeintel is not None and not self._require_tools:
            refresh_started = time.monotonic()
            self._codeintel.refresh()
            elapsed = time.monotonic() - refresh_started
            if elapsed >= 0.5:
                print(
                    f"[mango] codeintel refresh took {elapsed:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
        for path in paths:
            abs_path = self._abs_impl_path(path)
            file_path = Path(abs_path)
            if not file_path.is_file():
                continue
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            engine.remember_file(abs_path, source, iteration=iteration)

    def _display_path(self, abs_path: str) -> str:
        root = self._verification_root
        if root is not None:
            try:
                rel = Path(abs_path).resolve().relative_to(Path(root).resolve())
                return str(rel).replace("\\", "/")
            except ValueError:
                pass
        return Path(abs_path).name

    def _abs_impl_path(self, rel: str) -> str:
        return str(resolve_tool_path(rel, self._tool_context()))

    def _discover_test_files(self) -> list[str]:
        root = self._verification_root
        if root is None:
            return []
        base = Path(root)
        found: list[str] = []
        skip = {".venv", "venv", "__pycache__", ".git", ".mango", ".devdeck", "node_modules"}
        for path in base.rglob("test_*.py"):
            try:
                rel_parts = path.relative_to(base).parts
            except ValueError:
                rel_parts = path.parts
            if any(part in skip for part in rel_parts[:-1]):
                continue
            found.append(str(path.resolve()))
            if len(found) >= 12:
                break
        return found

    def _candidate_test_paths(self) -> list[str]:
        ordered: list[str] = []
        for rel in self._pending_goal_files:
            if not rel:
                continue
            candidate = Path(self._abs_impl_path(rel))
            name = candidate.name
            if candidate.is_file() and name.startswith("test_") and name.endswith(".py"):
                text = str(candidate)
                if text not in ordered:
                    ordered.append(text)
        for path in self._discover_test_files():
            if path not in ordered:
                ordered.append(path)
        return ordered[:12]

    def _impl_python_files(self) -> list[str]:
        root = self._verification_root
        if root is None:
            return []
        base = Path(root)
        found: list[str] = []
        skip = {".venv", "venv", "__pycache__", ".git", ".mango", ".devdeck", "node_modules", ".pytest_cache"}
        for path in base.rglob("*.py"):
            try:
                rel_parts = path.relative_to(base).parts
            except ValueError:
                rel_parts = path.parts
            if any(part in skip for part in rel_parts[:-1]):
                continue
            if path.name.startswith("test_"):
                continue
            found.append(str(path.resolve()))
        return found

    def _syntax_errors(self, paths: list[str] | None = None) -> list[str]:
        return collect_python_syntax_errors(paths if paths is not None else self._impl_python_files())

    def _mutated_python_paths(self, tool_results: list[ToolResult]) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for result in tool_results:
            if not result.success or result.tool_name not in _CODE_MUTATING_TOOLS:
                continue
            output = result.output if isinstance(result.output, dict) else {}
            raw = str(output.get("path") or output.get("absolute_path") or "")
            call = getattr(result, "call", None)
            arguments = getattr(call, "arguments", None) if call is not None else None
            if not raw and isinstance(arguments, dict):
                raw = str(arguments.get("path") or "")
            if not raw:
                continue
            abs_path = self._abs_impl_path(raw)
            if not abs_path.endswith(".py") or abs_path in seen:
                continue
            if not Path(abs_path).is_file():
                continue
            seen.add(abs_path)
            found.append(abs_path)
        return found

    def _enforce_syntax_after_mutation(
        self,
        engine: ContextEngine,
        tool_results: list[ToolResult],
        iteration: int,
        snapshots: dict[str, str] | None = None,
    ) -> bool:
        """Compile-check mutated .py files even when there is no test suite."""
        from mango_tools.syntax import python_syntax_error

        paths = self._mutated_python_paths(tool_results)
        if not paths:
            return False
        snaps = snapshots or {}
        kept_errors: list[str] = []
        restored = False
        for abs_path in paths:
            err = python_syntax_error(abs_path)
            if not err:
                continue
            previous = snaps.get(abs_path)
            if not previous or not previous.strip():
                kept_errors.append(err)
                continue
            try:
                current = Path(abs_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                current = ""
            prev_ok = python_syntax_error(abs_path, source=previous) is None
            truncated = len(current.strip()) < max(16, len(previous.strip()) // 2)
            if prev_ok or truncated:
                Path(abs_path).write_text(previous, encoding="utf-8")
                restored = True
                self._trace(f"iter {iteration} restored compiling {Path(abs_path).name}")
                if prev_ok:
                    continue
            kept_errors.append(err)
        self._syntax_broken = bool(kept_errors)
        if not kept_errors:
            if restored:
                engine.set_verification_feedback(
                    "Discarded a truncated write_file and restored the last compiling file. "
                    "Next write_file the tests (test_*.py), do not rewrite the implementation."
                )
            return False
        self._trace(f"iter {iteration} syntax_check FAIL {kept_errors[0][:180]}")
        self._apply_syntax_failure(engine, kept_errors, iteration=iteration, record=True)
        return True

    def _apply_syntax_failure(
        self,
        engine: ContextEngine,
        errors: list[str],
        *,
        iteration: int,
        record: bool,
    ) -> None:
        blob = "\n".join(f"- {item}" for item in errors)
        report = feedback(blob=blob)
        engine.state.verification_collection_error = True
        first = errors[0].split("\n", 1)[0]
        engine.state.verification_next_edit = f"Repair syntax with write_file: {first}"
        engine.state.verification_current_source = self._capture_impl_snapshot(engine)
        engine.set_verification_feedback(report)
        self._last_verification_report = report
        if record:
            self._last_verification_ok = False
            engine.note_raw_result(iteration, "syntax_check", False, report, error=report)
        if record or not self._syntax_emitted:
            self._syntax_emitted = True
            for item in errors:
                path, _, message = item.partition(":")
                self._emit(
                    agent_events.SYNTAX,
                    {"path": path.strip(), "message": (message or item).strip()},
                )

    def _seed_static_syntax(self, engine: ContextEngine) -> None:
        if not self._verification_enabled() or self._last_verification_ok is True:
            return
        errors = self._syntax_errors()
        if not errors:
            return
        self._apply_syntax_failure(engine, errors, iteration=1, record=False)

    def _capture_impl_snapshot(self, engine: ContextEngine) -> str:
        paths = [self._abs_impl_path(item) for item in engine.state.verification_impl_paths]
        paths.extend(self._pending_impl_files)
        paths.extend(self._impl_python_files())
        if not any(Path(item).is_file() for item in paths):
            for rel in engine.state.relevant_files:
                name = Path(rel).name
                if name.startswith("test_") or not str(rel).replace("\\", "/").endswith(".py"):
                    continue
                paths.append(self._abs_impl_path(rel))
        seen: set[str] = set()
        blocks: list[str] = []
        for abs_path in paths:
            if abs_path in seen:
                continue
            seen.add(abs_path)
            file_path = Path(abs_path)
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if not text:
                continue
            if len(text) > 480:
                text = text[:460].rstrip() + "\n..."
            blocks.append(f"{file_path.name} currently:\n{text}")
            self._pending_impl_files.append(abs_path)
            if len(blocks) >= 2:
                break
        return "\n".join(blocks)

    def _tool_context(self) -> dict[str, Any]:
        root = self._verification_root
        if root is None and self._codeintel is not None:
            root = getattr(self._codeintel, "root", None)
        ctx: dict[str, Any] = {}
        if root is not None:
            ctx["workspace"] = str(root)
        impl = self._plan_coverage_libraries()
        if impl:
            ctx["declared_libraries"] = impl
        if self._grounded_edits_enabled():
            ctx["require_grounded_edits"] = True
            ctx["files_read"] = tuple(self._files_read)
        return ctx

    def _snapshot_paths(self, tool_calls: list[Any]) -> dict[str, str]:
        snaps: dict[str, str] = {}
        for call in tool_calls:
            arguments = getattr(call, "arguments", None)
            if not isinstance(arguments, dict):
                continue
            path = arguments.get("path")
            if not path or path in {".", ""}:
                continue
            abs_path = self._abs_impl_path(str(path))
            file_path = Path(abs_path)
            if file_path.is_file():
                try:
                    snaps[abs_path] = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    snaps[abs_path] = ""
            else:
                snaps[abs_path] = ""
        return snaps

    @staticmethod
    def _tool_event_body(result: ToolResult) -> str:
        output = result.output if isinstance(result.output, dict) else {}
        if result.tool_name == "measure":
            median = output.get("median_ms")
            samples = output.get("samples_ms")
            err = str(output.get("stderr") or "").strip()
            parts = []
            if median is not None:
                parts.append(f"median {median} ms")
            if samples:
                parts.append("samples " + ", ".join(str(item) for item in samples))
            if err:
                parts.append(err[:400])
            return "\n".join(parts)[:1_500]
        if result.tool_name in {"ask_epistemic", "package_source_lookup", "doc_lookup"}:
            details = str(output.get("details") or "").strip()
            signature = str(output.get("signature") or "").strip()
            looked = output.get("looked_up")
            header = ""
            if isinstance(looked, list) and looked:
                header = "Looked up " + ", ".join(str(item) for item in looked if item)
            text = details or signature
            body = "\n\n".join(part for part in (header, text) if part)
            return body[:1_500]
        if isinstance(output, dict):
            parts = [
                str(output.get("stdout") or "").strip(),
                str(output.get("stderr") or "").strip(),
            ]
            details = str(output.get("details") or "").strip()
            if details and details not in parts:
                parts.append(details)
            libs = output.get("libraries")
            if isinstance(libs, list) and libs:
                parts.insert(0, "libraries: " + ", ".join(str(item) for item in libs))
            elif libs:
                parts.insert(0, f"libraries: {libs}")
            body = "\n".join(part for part in parts if part)
            if body:
                return body[:1_500]
        if result.error:
            return str(result.error)[:1_500]
        return ""

    def _emit_file_events(
        self,
        tool_results: list[ToolResult],
        snapshots: dict[str, str],
    ) -> None:
        for result in tool_results:
            name = result.tool_name
            arguments = getattr(getattr(result, "call", None), "arguments", None)
            if not isinstance(arguments, dict):
                arguments = {}
            output = result.output if isinstance(result.output, dict) else {}
            if name in _CODE_MUTATING_TOOLS and result.success:
                paths: list[str] = []
                if output.get("path"):
                    paths.append(str(output["path"]))
                for item in output.get("files") or []:
                    if isinstance(item, dict) and item.get("path"):
                        paths.append(str(item["path"]))
                if not paths and arguments.get("path") and arguments.get("path") not in {".", ""}:
                    paths.append(self._abs_impl_path(str(arguments["path"])))
                for path in paths:
                    abs_path = str(output.get("absolute_path") or self._abs_impl_path(path))
                    display_path = self._display_path(abs_path)
                    old = snapshots.get(abs_path, "")
                    try:
                        new = Path(abs_path).read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        new = ""
                    added, removed = agent_events.line_stats(old, new)
                    self._emit(
                        agent_events.FILE,
                        {
                            "action": "created" if not old and new else "edited",
                            "path": display_path,
                            "absolute_path": abs_path,
                            "added": added,
                            "removed": removed,
                            "diff": agent_events.unified_diff(abs_path, old, new),
                        },
                    )
                continue
            if name == "read_file" and result.success:
                path = str(output.get("path") or arguments.get("path") or "")
                content = str(output.get("content") or "")
                start, end = agent_events.read_range(content)
                abs_path = self._abs_impl_path(path) if path else path
                self._emit(
                    agent_events.FILE,
                    {
                        "action": "read",
                        "path": self._display_path(abs_path) if path else path,
                        "absolute_path": abs_path if path else None,
                        "start_line": start,
                        "end_line": end,
                    },
                )

    def _emit_tool_events(
        self,
        tool_calls: list[Any],
        tool_results: list[ToolResult],
        snapshots: dict[str, str],
        *,
        skip_files: bool = False,
    ) -> None:
        if not skip_files:
            self._emit_file_events(tool_results, snapshots)
        for idx, result in enumerate(tool_results):
            name = result.tool_name
            arguments = getattr(getattr(result, "call", None), "arguments", None)
            if not isinstance(arguments, dict):
                arguments = {}
            output = result.output if isinstance(result.output, dict) else {}
            blocked = bool(result.metadata.get("blocked")) or (
                not result.success and "BLOCKED" in str(result.error or "")
            )
            if blocked and name in _CODE_MUTATING_TOOLS:
                path = str(arguments.get("path") or "")
                title = f"Runner blocked {name}"
                if path:
                    title = f"Runner blocked {self._display_path(self._abs_impl_path(path))}"
                self._emit(
                    agent_events.TOOL,
                    {
                        "name": name,
                        "title": title,
                        "body": str(result.error or "")[:1_500],
                        "ok": False,
                        "blocked": True,
                        "streaming": False,
                    },
                )
                continue
            if name in _CODE_MUTATING_TOOLS or name == "read_file":
                # Still close streaming explore chips for reads.
                if name == "read_file":
                    path = str(
                        (output.get("path") if isinstance(output, dict) else None)
                        or arguments.get("path")
                        or ""
                    )
                    title = agent_events.tool_title("read_file", {"path": path} if path else arguments)
                    self._emit(
                        agent_events.TOOL,
                        {
                            "id": f"tool-read_file-{self._run_id}-{self._current_iteration}-{idx}",
                            "name": name,
                            "title": title,
                            "streaming": False,
                            "ok": bool(result.success),
                        },
                    )
                continue
            if name in {
                "run_tests",
                "search_code",
                "codebase_lookup",
                "run_terminal_command",
                "measure",
                "ask_epistemic",
                "declare_apis",
            } | _RESEARCH_TOOLS:
                body = self._tool_event_body(result)
                ok = None
                title = agent_events.tool_title(name, arguments)
                if isinstance(output, dict) and name == "run_tests":
                    ok = bool(output.get("ok"))
                    title = "Ran tests" if ok else "Tests failed"
                elif isinstance(output, dict) and name == "measure":
                    ok = bool(output.get("ok"))
                    median = output.get("median_ms")
                    title = f"Measured {median} ms" if median is not None else agent_events.tool_title(name, arguments)
                tool_id = None
                if name == "run_tests":
                    tool_id = f"tool-run-tests-{self._run_id}-{self._current_iteration}"
                elif name == "ask_epistemic":
                    tool_id = f"tool-ask-epistemic-{self._run_id}-{self._current_iteration}"
                elif name == "declare_apis":
                    tool_id = f"tool-declare-apis-{self._run_id}-{self._current_iteration}"
                elif name in {
                    "search_code",
                    "read_file",
                    "run_terminal_command",
                    "measure",
                    "codebase_lookup",
                }:
                    tool_id = f"tool-{name}-{self._run_id}-{self._current_iteration}-{idx}"
                payload: dict[str, Any] = {
                    "name": name,
                    "title": title,
                    "body": body or None,
                    "console": name in {"run_tests", "run_terminal_command", "measure"},
                    "ok": ok if ok is not None else bool(result.success),
                    "streaming": False,
                }
                if tool_id:
                    payload["id"] = tool_id
                self._emit(agent_events.TOOL, payload)

    def _rename_still_needed(self) -> bool:
        if not self._rename_pair:
            return False
        root = self._verification_root
        if root is None:
            return False
        old, new = self._rename_pair
        try:
            from mango_tools.implementations.rename_symbol import (
                _python_files,
                _rename_identifiers,
            )
        except ImportError:
            return False
        for file_path in _python_files(Path(root)):
            try:
                source = file_path.read_text(encoding="utf-8")
            except OSError:
                continue
            _, count = _rename_identifiers(source, old, new)
            if count:
                return True
        return False

    def _apply_pending_rename(self, engine: ContextEngine, iteration: int) -> bool:
        if not self._rename_pair:
            return False
        old, new = self._rename_pair
        try:
            tool = self._registry.get("rename_symbol")
            output = tool.handler(
                old_name=old,
                new_name=new,
                path=".",
                _context=self._tool_context(),
            )
        except Exception as exc:  # noqa: BLE001
            engine.set_verification_feedback(feedback(old=old, new=new, exc=exc))
            self._last_verification_ok = False
            return False
        engine.note_raw_result(iteration, "rename_symbol", True, json.dumps(output, ensure_ascii=False))
        self._remember_code_results(
            engine,
            [ToolResult(success=True, tool_name="rename_symbol", output=output)],
            iteration,
        )
        return True

    def _block_incomplete_rename(self, engine: ContextEngine) -> None:
        old, new = self._rename_pair or ("", "")
        hint = f'Call rename_symbol with {{"old_name": "{old}", "new_name": "{new}", "path": "."}}'
        engine.state.verification_next_edit = hint
        engine.set_verification_feedback(
            feedback(old=old, hint=hint)
        )
        self._last_verification_ok = False

    def _abort_report(self) -> str:
        compact = self._last_verification_report.strip() or "Verification failed."
        return feedback(
            failed=self._failed_verifications,
            max=self._limits.max_fix_attempts,
            report=compact,
        )


def _looks_like_test_path(path: str) -> bool:
    normalized = normalize_tool_path(path).replace("\\", "/")
    name = Path(normalized).name.lower()
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    parts = [part.lower() for part in Path(normalized).parts]
    return any(part in _TEST_DIR_NAMES for part in parts[:-1])


def _symbol_from_edit_args(arguments: dict[str, Any]) -> str | None:
    symbol = arguments.get("symbol")
    if isinstance(symbol, str) and symbol.isidentifier():
        return symbol
    for key in ("old_string", "new_string", "body"):
        text = arguments.get(key)
        if not isinstance(text, str):
            continue
        match = _DEF_OR_CLASS.search(text)
        if match:
            return match.group(1)
    return None


def _is_follow_up_goal(task: str) -> bool:
    blob = (task or "").lower()
    return any(marker in blob for marker in _FOLLOW_UP_MARKERS)


def _looks_like_script(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hits = 0
    for line in lines:
        if line.startswith(("import ", "from ", "def ", "class ")):
            hits += 1
    return hits >= 3


def _should_write_file_fallback(new_string: str, existing: str) -> bool:
    if not _looks_like_script(new_string):
        return False
    if not existing:
        return True
    return len(new_string) >= max(int(len(existing) * 0.5), 40)


def _looks_like_api_dump(text: str) -> bool:
    blob = " ".join((text or "").split())
    return blob.count(" | ") >= 3 and blob.count("(") >= 3


def _clean_finish_summary(text: str) -> str:
    cleaned = (text or "").strip()
    cut = re.search(r"<tool_call\b", cleaned, flags=re.IGNORECASE)
    if cut:
        cleaned = cleaned[: cut.start()].strip()
    cleaned = _FENCE_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if len(cleaned) > 1600:
        cleaned = cleaned[:1597].rstrip() + "..."
    return cleaned


def _is_good_finish_summary(text: str) -> bool:
    blob = " ".join((text or "").split())
    if len(blob) < 80:
        return False
    low = blob.lower()
    if "<tool_call" in low or "```" in text:
        return False
    if low in {"done", "all done.", "all tests passed.", "tests passed."}:
        return False
    if low.startswith("i will ") or low.startswith("next i "):
        return False
    return True


def _finish_lies_about_tests(text: str, tests_ok: bool) -> bool:
    if tests_ok:
        return False
    low = (text or "").lower()
    return any(
        token in low
        for token in (
            "tests passed",
            "all tests",
            "tests laufen",
            "erfolgreich durch",
            "successfully through",
        )
    )


def _thought_sentence_count(text: str) -> int:
    compact = " ".join(text.split()).strip()
    if not compact:
        return 0
    parts = re.split(r"(?<=[.!?])\s+", compact)
    return len([p for p in parts if p.strip()])


def _sanitize_thought(
    text: str,
    *,
    max_sentences: int = 2,
    max_chars: int = 280,
) -> tuple[str, bool]:
    """Strip tool markup, think tags, code fences, and dumped scripts from the visible thought."""
    if not text:
        return "", False
    had_markup = (
        "<tool_call" in text.lower()
        or "```" in text
        or "redacted_thinking" in text.lower()
        or "<think" in text.lower()
        or _looks_like_script(text)
        or _looks_like_api_dump(text)
    )
    cleaned = strip_thought_markup(text)
    if _looks_like_script(cleaned):
        kept: list[str] = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ", "def ", "class ")):
                continue
            if stripped.startswith(("if __name__", "try:", "except ", "with ")):
                continue
            kept.append(line)
        cleaned = "\n".join(kept)
    if _looks_like_api_dump(cleaned):
        cleaned = ""
    display = " ".join(cleaned.split()).strip()
    sentences = re.split(r"(?<=[.!?])\s+", display)
    sentences = [s.strip() for s in sentences if s.strip()]
    cap = max(1, int(max_sentences))
    if len(sentences) > cap:
        display = " ".join(sentences[:cap])
    limit = max(40, int(max_chars))
    if len(display) > limit:
        display = display[: max(0, limit - 3)] + "..."
    return display, had_markup


def _snippet_around_symbol(path: str, symbol: str | None) -> str:
    if not symbol:
        return ""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = content.splitlines()
    needle_def = f"def {symbol}"
    needle_class = f"class {symbol}"
    hit_i = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(needle_def) or stripped.startswith(needle_class):
            hit_i = i
            break
    if hit_i is None:
        return ""
    start_i = max(0, hit_i - 5)
    end_i = min(len(lines), hit_i + 25)
    return "\n".join(lines[start_i:end_i]).strip()[:1500]


def _compact_args(arguments: dict[str, Any] | None, *, limit: int = 180) -> str:
    if not arguments:
        return ""
    parts: list[str] = []
    for key, value in arguments.items():
        text = str(value).replace("\n", "\\n")
        if key in {"content", "body", "old_string", "new_string"} and len(text) > 80:
            text = text[:79] + "…"
        parts.append(f"{key}={text}")
    blob = " ".join(parts)
    if len(blob) > limit:
        return blob[: limit - 1] + "…"
    return blob


def _compact_result(result: ToolResult) -> str:
    output = result.output if isinstance(result.output, dict) else {}
    if isinstance(output, dict):
        path = output.get("path") or output.get("absolute_path")
        if path:
            return str(path)
        count = output.get("match_count")
        if count is not None:
            return f"matches={count}"
        replacements = output.get("replacements")
        if replacements is not None:
            return f"replacements={replacements}"
    return ""


def _compact_lookup(data: dict[str, Any]) -> str:
    impact = data.get("impact") if isinstance(data.get("impact"), dict) else {}
    slim = {
        "query": data.get("query"),
        "kind": data.get("kind"),
        "symbol": data.get("symbol"),
        "definitions": data.get("definitions") or [],
        "files": [
            {"path": item.get("path"), "score": item.get("score")}
            for item in (data.get("files") or [])[:8]
            if isinstance(item, dict)
        ],
        "impact": {
            "dependent_files": list(impact.get("dependent_files") or [])[:8],
            "test_files": list(impact.get("test_files") or [])[:6],
            "signatures": list(impact.get("signatures") or [])[:6],
        }
        if impact
        else None,
    }
    return json.dumps(slim, ensure_ascii=False)


def _parse_libraries(raw: str) -> list[str]:
    text = str(raw or "").replace(";", ",").replace("\n", ",")
    names: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        name = part.strip().strip("'\"")
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _merge_limits(limits: AgentLimits | None, **overrides: Any) -> AgentLimits:
    base = limits or AgentLimits()
    values = {
        "max_iterations": base.max_iterations,
        "max_runtime_seconds": base.max_runtime_seconds,
        "max_reasoning_cycles": base.max_reasoning_cycles,
        "max_fix_attempts": base.max_fix_attempts,
        "max_epistemic_iterations": base.max_epistemic_iterations,
        "max_prompt_chars": base.max_prompt_chars,
    }
    for key, value in overrides.items():
        if value is not None:
            values[key] = value
    return AgentLimits(**values)


def create_agent(
    *,
    runtime_config: str | None = None,
    max_iterations: int | None = 10,
    max_tokens: int | None = 2048,
    load_model: bool = True,
    **kwargs: Any,
) -> Agent:
    """Convenience factory using the default runtime config and built-in tools."""
    from mango_runtime import ModelRunner

    runner = ModelRunner(runtime_config)
    if load_model:
        runner.load()
    return Agent(runner, max_iterations=max_iterations, max_tokens=max_tokens, **kwargs)
