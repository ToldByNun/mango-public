"""Load CoT reasoning prompts from markdown files in the repo `prompts/` folder."""

from __future__ import annotations

import os
from pathlib import Path

_PROMPT_ENV = "MANGO_PROMPTS_DIR"


def load_system_prompt(name: str, *, start: Path | None = None) -> str:
    filename = f"{name}.md"
    for path in _prompt_candidates(filename, start=start or Path(__file__).resolve()):
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(
        f"system prompt {filename!r} not found. Put it in the repo prompts/ folder "
        f"or set {_PROMPT_ENV}."
    )


def render_system_prompt(name: str, *, start: Path | None = None, **values: str) -> str:
    text = load_system_prompt(name, start=start)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


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
