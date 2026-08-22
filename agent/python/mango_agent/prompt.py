"""Load system prompts from markdown files in the repo `prompts/` folder."""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path
from typing import Any

_PROMPT_ENV = "MANGO_PROMPTS_DIR"
_FEEDBACK_HEADING = re.compile(r"^#\s+([A-Za-z_][A-Za-z0-9_.]*)\s*$")
_FEEDBACK_STATE: tuple[str, float, dict[str, str]] | None = None
_SKIP_CALLERS = frozenset({"feedback", "_caller_function", "<genexpr>", "<lambda>", "<listcomp>"})


def load_system_prompt(name: str, *, start: Path | None = None) -> str:
    """Return the text of `prompts/<name>.md` (repo root, or MANGO_PROMPTS_DIR)."""
    path = _find_prompt_file(f"{name}.md", start=start)
    return path.read_text(encoding="utf-8").strip()


def render_system_prompt(name: str, *, start: Path | None = None, **values: str) -> str:
    """Load a prompt and replace `{{key}}` placeholders."""
    return _fill(load_system_prompt(name, start=start), values)


def feedback(name: str = "", **values: Any) -> str:
    """Return a runner snippet from `prompts/feedback.md`.

    Lookup order:
    1. Exact heading `# name` when `name` is passed.
    2. `# caller.name` (caller = the Python function that called `feedback`).
    3. `# caller` when `name` is empty.
    """
    sections = _feedback_sections()
    caller = _caller_function()
    keys: list[str] = []
    if name:
        keys.append(name)
        if caller:
            keys.append(f"{caller}.{name}")
    elif caller:
        keys.append(caller)
    for key in keys:
        text = sections.get(key)
        if text is not None:
            return _fill(text, values)
    looked = ", ".join(f"#{key}" for key in keys) or "#<empty>"
    raise KeyError(f"prompts/feedback.md has no section {looked}")


def parse_feedback_sections(text: str) -> dict[str, str]:
    """Parse `# heading` blocks from a feedback markdown file."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        match = _FEEDBACK_HEADING.match(line)
        if match:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = match.group(1)
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _find_prompt_file(filename: str, *, start: Path | None = None) -> Path:
    for path in _prompt_candidates(filename, start=start or Path(__file__).resolve()):
        if path.is_file():
            return path
    searched = "\n".join(
        f"  - {path}" for path in _prompt_candidates(filename, start=start or Path(__file__).resolve())
    )
    raise FileNotFoundError(
        f"system prompt {filename!r} not found. Put it in the repo prompts/ folder "
        f"or set {_PROMPT_ENV}. Looked at:\n{searched}"
    )


def _feedback_sections() -> dict[str, str]:
    global _FEEDBACK_STATE
    path = _find_prompt_file("feedback.md")
    mtime = path.stat().st_mtime
    key = str(path.resolve())
    cached = _FEEDBACK_STATE
    if cached is not None and cached[0] == key and cached[1] == mtime:
        return cached[2]
    sections = parse_feedback_sections(path.read_text(encoding="utf-8"))
    _FEEDBACK_STATE = (key, mtime, sections)
    return sections


def _caller_function() -> str:
    frame = inspect.currentframe()
    try:
        here = frame
        while here is not None:
            name = here.f_code.co_name
            if name not in _SKIP_CALLERS and not name.startswith("<"):
                return name
            here = here.f_back
    finally:
        del frame
    return ""


def _fill(text: str, values: dict[str, Any]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text.strip()


def _prompt_candidates(filename: str, *, start: Path) -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get(_PROMPT_ENV)
    if env:
        paths.append(Path(env).expanduser() / filename)
    here = start if start.is_dir() else start.parent
    for parent in [here, *here.parents]:
        paths.append(parent / "prompts" / filename)
    paths.append(Path.cwd() / "prompts" / filename)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


_LEVEL_SUFFIX = {
    "think": "agent_think",
    "deep": "agent_deep",
    "max": "agent_max",
}


def compose_agent_system_prompt(level: str | None = None, *, start: Path | None = None) -> str:
    """Base agent prompt (variant-aware) plus an optional thinking-level suffix."""
    base_name = _prompt_variant_name()
    base = load_system_prompt(base_name, start=start)
    name = _LEVEL_SUFFIX.get(str(level or "off").strip().lower(), "")
    if not name:
        return base
    extra = load_system_prompt(name, start=start)
    return f"{base}\n\n{extra}".strip()


def _prompt_variant_name() -> str:
    """Select agent.md (v1) or agent_v2.md via MANGO_PROMPT_VARIANT / flags."""
    try:
        from mango_agent.flags import prompt_variant

        variant = prompt_variant()
    except Exception:
        variant = os.environ.get("MANGO_PROMPT_VARIANT", "v2").strip().lower() or "v2"
    if variant in {"v2", "ab_test"}:
        return "agent_v2"
    return "agent"


DEFAULT_SYSTEM_PROMPT = load_system_prompt("agent")
SWE_BENCH_SYSTEM_PROMPT = load_system_prompt("swebench")
EPISTEMIC_SYSTEM_PROMPT = load_system_prompt("epistemic")
