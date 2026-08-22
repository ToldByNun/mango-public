"""Deterministic work plan seeded at run start and kept in every prompt."""

from __future__ import annotations

import re

from mango_agent.impl_completeness import goal_wants_runnable_script, required_features

_GOAL_WANTS_TESTS = re.compile(r"(?i)test_|pytest|\btests?\b|\bteste")


def build_work_plan(task: str) -> str:
    """Build a step list from the goal — no LLM, always reproducible."""
    lines = [
        "Work plan (runner keeps this visible; follow in order):",
    ]
    step = 1
    if goal_wants_runnable_script(task):
        lines.append(
            f"{step}. write_file the COMPLETE CLI module "
            "(argparse subcommands + handler functions + if __name__ == '__main__')"
        )
        step += 1
        lines.append(
            f"{step}. read_file the module to verify the ACTUAL source "
            "(functions present/missing — never guess from byte size or `type`)"
        )
        step += 1
    else:
        lines.append(f"{step}. read_file / search_code to locate the target before editing")
        step += 1
        lines.append(f"{step}. edit_file or write_file with a complete, working change")
        step += 1

    for feature in required_features(task):
        lines.append(f"{step}. Implement: {feature}")
        step += 1

    if _GOAL_WANTS_TESTS.search(task or ""):
        lines.append(f"{step}. write_file test_*.py, then let the runner execute tests")
        step += 1

    lines.append(
        f"{step}. Finish ONLY when ## Implementation status reports no gaps "
        "(all handlers + main entry present)"
    )
    return "\n".join(lines)
