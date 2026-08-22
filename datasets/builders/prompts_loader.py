from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"


def load_prompt(name: str) -> str:
    path = PROMPTS / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8").strip()


def agent_system() -> str:
    return load_prompt("agent_v2.md")


def security_system() -> str:
    return load_prompt("security_review.md")


def epistemic_system() -> str:
    return load_prompt("epistemic.md")


def finish_system() -> str:
    return agent_system()
