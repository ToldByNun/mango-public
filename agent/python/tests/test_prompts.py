from __future__ import annotations

from pathlib import Path

from mango_agent.prompt import (
    DEFAULT_SYSTEM_PROMPT,
    EPISTEMIC_SYSTEM_PROMPT,
    SWE_BENCH_SYSTEM_PROMPT,
    compose_agent_system_prompt,
    feedback,
    load_system_prompt,
    parse_feedback_sections,
    render_system_prompt,
)
from mango_agent.prompt import _prompt_variant_name
from mango_cot.prompt import render_system_prompt as render_cot_prompt


def test_system_prompts_load_from_markdown() -> None:
    root = Path(__file__).resolve().parents[3] / "prompts"
    assert (root / "agent_v2.md").is_file()
    assert "declare_apis" in DEFAULT_SYSTEM_PROMPT
    assert "write_file" in DEFAULT_SYSTEM_PROMPT
    assert "research_codebase" in DEFAULT_SYSTEM_PROMPT
    assert "AGENT PROTOCOL" in DEFAULT_SYSTEM_PROMPT
    assert "GitHub issue" in SWE_BENCH_SYSTEM_PROMPT
    assert "old_string" in SWE_BENCH_SYSTEM_PROMPT
    assert "API Agent" in EPISTEMIC_SYSTEM_PROMPT or "epistemic" in EPISTEMIC_SYSTEM_PROMPT.lower()
    assert "usage brief" in EPISTEMIC_SYSTEM_PROMPT.lower() or "usage" in EPISTEMIC_SYSTEM_PROMPT.lower()
    assert load_system_prompt("agent_v2") == DEFAULT_SYSTEM_PROMPT
    assert "finish message" in load_system_prompt("summary").lower() or "summary" in load_system_prompt("summary").lower()
    assert "measure" in DEFAULT_SYSTEM_PROMPT
    assert "natural-language" in load_system_prompt("cot").lower() or "natural language" in load_system_prompt("cot").lower()


def test_thinking_level_prompts_compose() -> None:
    off = compose_agent_system_prompt("off")
    think = compose_agent_system_prompt("think")
    deep = compose_agent_system_prompt("deep")
    maxed = compose_agent_system_prompt("max")
    assert off == load_system_prompt(_prompt_variant_name())
    assert off == load_system_prompt("agent_v2")
    assert "THINKING LEVEL: think" in think
    assert "AGENT PROTOCOL" in think
    assert "research_codebase" in think
    assert "THINKING LEVEL: deep" in deep
    assert "inspect" in deep.lower()
    assert "THINKING LEVEL: max" in maxed
    assert "Verify" in maxed or "verify" in maxed.lower()
    assert load_system_prompt("agent_think") == think
    assert load_system_prompt("agent_deep") == deep
    assert load_system_prompt("agent_max") == maxed


def test_title_prompt_renders_goal() -> None:
    text = render_system_prompt("title", goal="fix the login bug")
    assert "fix the login bug" in text
    assert "{{goal}}" not in text


def test_feedback_md_lookup_by_function_heading() -> None:
    sections = parse_feedback_sections(load_system_prompt("feedback"))
    assert "_handle_run_tests_results.stress" in sections
    assert "ThreadPoolExecutor" in sections["_handle_run_tests_results.stress"]
    assert "package_source_lookup" in sections["research_next"]
    assert "usage brief" in sections["research_summarize"].lower()
    assert "per-client" in sections["review_message.coarsened"].lower()

    exact = feedback("review_message.coarsened")
    assert "global lock" in exact.lower()
    assert "{{" not in exact

    assert "short" in feedback("run.truncated_json").lower() or "fence" in feedback("run.truncated_json").lower()
    assert "missing" in feedback("missing_dependency", pkgs="discord", command="pip install discord.py").lower()

    def _handle_run_tests_results() -> str:
        return feedback("stress")

    assert "ThreadPoolExecutor" in _handle_run_tests_results()
    assert "{{libs}}" not in feedback("_note_plan_progress.declare", libs="pandas")
    assert "pandas" in feedback("_note_plan_progress.declare", libs="pandas")
    assert "Skip ask_epistemic" in feedback("_note_plan_progress.stdlib_ok", libs="argparse, csv")
    text = render_system_prompt("title", goal="fix the login bug")
    assert "fix the login bug" in text
    assert "{{goal}}" not in text
    assert "experiment.reverted" in sections
    assert "experiment.kept" in sections
    assert "experiment.unsupported" in sections
    assert "next hypothesis must differ" in sections["experiment.reverted"].lower()


def test_cot_prompt_renders_placeholders() -> None:
    text = render_cot_prompt(
        "cot",
        marker="[Mango reasoning cycle]",
        mode="EXTENDED",
        goal="fix clamp",
        snapshot="files: mathutil.py",
        prior="search first",
        schema='{"next_action": "string"}',
        mode_hint="Update decisions.",
    )
    assert "[Mango reasoning cycle]" in text
    assert "EXTENDED" in text
    assert "fix clamp" in text
    assert "{{goal}}" not in text
    assert "thought" in text.lower()
    assert "natural" in text.lower()


def test_every_feedback_call_site_resolves() -> None:
    """A missing snippet raises KeyError mid-run, so catch it here instead."""
    import ast

    import mango_agent

    sections = parse_feedback_sections(load_system_prompt("feedback"))
    package = Path(mango_agent.__file__).resolve().parent
    missing: list[str] = []
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scopes: dict[ast.AST, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    scopes.setdefault(child, node.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "feedback"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            name = node.args[0].value
            if not isinstance(name, str):
                continue
            caller = scopes.get(node, "")
            if name in sections or f"{caller}.{name}" in sections:
                continue
            missing.append(f"{path.name}:{node.lineno} feedback({name!r}) in {caller or '<module>'}()")
    assert not missing, "feedback sections missing from prompts/feedback.md:\n" + "\n".join(missing)
