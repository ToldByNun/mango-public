"""Unit tests for the coding-phase state machine and close-the-loop gates."""

from __future__ import annotations

from pathlib import Path

from mango_agent import Agent
from mango_agent.coding_phase import CodingPhase, resolve_coding_phase
from mango_agent.prompt import feedback
from mango_context import ContextEngine
from mango_tools import create_default_registry
from mango_tools.types import ToolCall, ToolResult
from test_agent_loop import FakeModelRunner

DISCORD_GOAL = (
    "Schreib einen Discord-Bot der Nachrichten an LM Studio (localhost:1234) "
    "weiterleitet und die Antwort zurücksendet."
)

HOLLOW = """\
import os
import discord
from discord.ext import commands

TOKEN = os.environ.get("DISCORD_TOKEN", "")
bot = commands.Bot(command_prefix="!")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
"""

BROKEN = HOLLOW + "\n    if True\n        pass\n"


def test_resolve_syntax_beats_logic_gaps() -> None:
    phase = resolve_coding_phase(
        plan_gate_phase=None,
        syntax_broken=True,
        collection_error=False,
        primary_impl_exists=True,
        has_logic_gaps=True,
        task_wants_tests=False,
        ran_tests_ok=False,
        test_files_exist=False,
        tests_uncollectable=False,
    )
    assert phase is CodingPhase.CODE_REPAIR


def test_resolve_extend_when_gaps_and_syntax_ok() -> None:
    phase = resolve_coding_phase(
        plan_gate_phase=None,
        syntax_broken=False,
        collection_error=False,
        primary_impl_exists=True,
        has_logic_gaps=True,
        task_wants_tests=False,
        ran_tests_ok=False,
        test_files_exist=False,
        tests_uncollectable=False,
    )
    assert phase is CodingPhase.CODE_EXTEND


def test_resolve_complete_when_no_file() -> None:
    phase = resolve_coding_phase(
        plan_gate_phase=None,
        syntax_broken=False,
        collection_error=False,
        primary_impl_exists=False,
        has_logic_gaps=False,
        task_wants_tests=False,
        ran_tests_ok=False,
        test_files_exist=False,
        tests_uncollectable=False,
    )
    assert phase is CodingPhase.CODE_COMPLETE


def test_syntax_broken_forces_write_not_insert(tmp_path: Path) -> None:
    target = tmp_path / "discord_bot.py"
    target.write_text(BROKEN, encoding="utf-8")
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = DISCORD_GOAL
    agent._cli_goal = True
    agent._require_tools = True
    agent._acted_once = True
    agent._syntax_broken = True
    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._context = engine
    agent._refresh_impl_completeness(engine)
    # Even with logic gaps from the hollow/broken file, REPAIR wins.
    assert agent._resolve_coding_phase() is CodingPhase.CODE_REPAIR
    assert agent._forced_tool_name() == "write_file"
    filtered = agent._apply_grammar_filters(list(agent._enabled_registry_names()))
    assert filtered == ["write_file"]


def test_hollow_skeleton_write_rejected_for_discord(tmp_path: Path) -> None:
    target = tmp_path / "discord_bot.py"
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = DISCORD_GOAL
    agent._cli_goal = True
    agent._require_tools = True
    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._context = engine
    # Simulate a successful hollow write.
    target.write_text(HOLLOW, encoding="utf-8")
    agent._last_mutation_snapshots = {str(target.resolve()): ""}
    call = ToolCall(
        name="write_file",
        arguments={"path": str(target), "content": HOLLOW},
        raw="",
        start=0,
        end=0,
    )
    result = ToolResult(success=True, tool_name="write_file", output={"path": str(target)}, call=call)
    out = agent._reject_hollow_skeleton_writes([result], engine)
    assert out is not None
    assert out[0].success is False
    assert "hollow" in (out[0].error or "").lower() or "skeleton" in (out[0].error or "").lower()
    # Skeleton stays on disk so the next turn can insert_lines (not rewrite thrash).
    assert target.exists()
    assert "discord" in target.read_text(encoding="utf-8").lower() or "Bot" in target.read_text(encoding="utf-8")
    assert agent._prefer_insert_lines is True


def test_gap_unchanged_mutation_reverted(tmp_path: Path) -> None:
    target = tmp_path / "discord_bot.py"
    original = HOLLOW
    target.write_text(original, encoding="utf-8")
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = DISCORD_GOAL
    agent._cli_goal = True
    agent._require_tools = True
    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._context = engine
    agent._refresh_impl_completeness(engine)
    gaps_before = list(agent._impl_gaps)
    assert gaps_before

    # Insert that doesn't close HTTP/send/run/incomplete gaps (module-level noise).
    useless = (
        "\n# noise pad — does not implement HTTP/send/run\n"
        "NOISE_A = 1\n"
        "NOISE_B = 2\n"
        "NOISE_C = 3\n"
        "NOISE_D = 4\n"
        "NOISE_E = 5\n"
        "NOISE_F = 6\n"
        "NOISE_G = 7\n"
    )
    target.write_text(original + useless, encoding="utf-8")
    agent._last_mutation_snapshots = {str(target.resolve()): original}
    call = ToolCall(
        name="insert_lines",
        arguments={"path": str(target), "line": 99, "content": useless},
        raw="",
        start=0,
        end=0,
    )
    result = ToolResult(
        success=True,
        tool_name="insert_lines",
        output={"path": str(target), "lines_inserted": 8},
        call=call,
    )
    out = agent._reject_unchanged_gap_mutations(engine, [result], gaps_before)
    assert out[0].success is False
    assert target.read_text(encoding="utf-8") == original


def test_coding_phase_feedback_templates_exist() -> None:
    assert "CODE_COMPLETE" in feedback("coding_complete", path="bot.py")
    assert "CODE_EXTEND" in feedback(
        "coding_extend", path="bot.py", line="19", gaps="- http"
    )
    assert "CODE_REPAIR" in feedback("coding_repair", path="bot.py")
    assert "BLOCKED" in feedback(
        "gap_not_closed", path="bot.py", line="19", gaps="- http"
    )
    assert "hollow" in feedback(
        "hollow_skeleton_blocked", path="bot.py", min_lines="40", gaps="- http"
    ).lower()


def test_attention_slim_hides_work_plan() -> None:
    from mango_context.prompt_window import build_prompt
    from mango_context.types import ContextState

    state = ContextState(
        goal="build a discord bot",
        work_plan="1. do lots of planning\n2. more planning\n3. even more",
        verification_feedback="PHASE=CODE_EXTEND | NEXT=insert_lines",
        coding_attention_slim=True,
        system_prompt="sys",
    )
    prompt = build_prompt(state)
    assert "## Work plan" not in prompt
    assert "## Focus" in prompt
    assert "CODE NOW" in prompt


def test_finish_summary_strips_think_and_rejects_meta() -> None:
    from mango_agent.agent import _clean_finish_summary, _is_good_finish_summary

    think = (
        "<think>\n"
        "Looking at the Facts: changed_files: no files recorded. "
        "I need to be honest. Let me re-read the instructions. "
        "If Facts show no file changes this was Q&A...\n"
        "</think>\n"
        "I created discord_bot.py with LM Studio wiring."
    )
    cleaned = _clean_finish_summary(think)
    assert "<think" not in cleaned.lower()
    assert "re-read the instructions" not in cleaned.lower()
    # Meta-only dumps must not pass as a good finish.
    meta = (
        "Looking at the Facts carefully: changed_files: no files recorded and "
        "tests: not confirmed. I need to be honest about what happened and "
        "re-read the instructions about ASK / READ-ONLY runs."
    )
    assert _is_good_finish_summary(meta) is False
    good = (
        "Created discord_bot.py. It listens for channel messages, forwards them "
        "to the local LM Studio chat-completions API, and posts the model reply."
    )
    assert _is_good_finish_summary(good) is True


def test_fallback_summary_is_concrete_not_placeholders(tmp_path: Path) -> None:
    target = tmp_path / "discord_bot.py"
    target.write_text(
        "import discord\nimport requests\n"
        "bot = discord.Client(intents=discord.Intents.default())\n"
        "async def on_message(m):\n"
        "    r = requests.post('http://localhost:1234/v1/chat/completions', json={})\n"
        "    await m.channel.send(r.text)\n"
        "bot.run('t')\n",
        encoding="utf-8",
    )
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = DISCORD_GOAL
    agent._cli_goal = True
    agent._require_tools = True
    agent._acted_once = True
    text = agent._fallback_summary([])
    assert "{{" not in text
    assert "<think" not in text.lower()
    assert "discord_bot.py" in text
    assert "HTTP" in text or "http" in text.lower()
    out = agent._write_finish_summary([], draft="<think>meta dump about Facts</think>")
    assert "{{" not in out
    assert "changed_files" not in out
    assert "Wrote:" in out or "Geschrieben:" in out or "discord_bot.py" in out
