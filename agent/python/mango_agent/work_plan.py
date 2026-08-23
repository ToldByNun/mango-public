"""Deterministic work plan seeded at run start and kept in every prompt."""

from __future__ import annotations

import re

from mango_agent.impl_completeness import goal_wants_runnable_script, required_features

_GOAL_WANTS_TESTS = re.compile(r"(?i)test_|pytest|\btests?\b|\bteste")
_INTEGRATION = re.compile(
    r"(?i)\b(discord|telegram|slack\s+bot|webhook|lm\s*studio|ollama|fastapi|flask)\b"
)
_INVENTORY = re.compile(r"(?i)\binventory\b|\badd/remove\b|\bsubcommand")


def build_work_plan(task: str) -> str:
    """Short step list from the goal — keep it tiny for small-model attention."""
    lines: list[str] = []
    step = 1
    text = task or ""
    if _INTEGRATION.search(text) and goal_wants_runnable_script(text):
        lines.append(
            f"{step}. write_file COMPLETE bot (handlers + HTTP + send/reply + entry) "
            f"— OR — skeleton ≤15 lines then insert_lines ONE fenced block (all logic)"
        )
        step += 1
    elif goal_wants_runnable_script(text) and _INVENTORY.search(text):
        lines.append(
            f"{step}. write_file SHORT skeleton (<40 lines) then edit_file one feature at a time"
        )
        step += 1
    elif goal_wants_runnable_script(text):
        lines.append(f"{step}. write_file the COMPLETE module (imports + logic + entry)")
        step += 1
    else:
        lines.append(f"{step}. write_file (or edit_file after one read_file)")
        step += 1

    for feature in required_features(text)[:4]:
        lines.append(f"{step}. Implement: {feature}")
        step += 1

    if _GOAL_WANTS_TESTS.search(text):
        lines.append(f"{step}. write_file test_*.py → runner runs pytest")
        step += 1

    lines.append(f"{step}. Finish when Goal is met")
    return "\n".join(lines)
