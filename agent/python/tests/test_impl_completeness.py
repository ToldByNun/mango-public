from __future__ import annotations

from pathlib import Path

from mango_agent import Agent, StopReason
from mango_agent.impl_completeness import (
    find_impl_gaps,
    goal_wants_runnable_script,
    summarize_impl_status,
)
from mango_tools import create_default_registry
from test_agent_loop import FakeModelRunner

STUB_INVENTORY = """\
# inventory.py
import argparse
import json
import os

DB_FILE = "inventory.json"


def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": {}}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def add_item(db, name, count=1, description=""):
    items = db["items"]
    #
"""


COMPLETE_CLI = STUB_INVENTORY.replace(
    '    items = db["items"]\n    #',
    """    items = db["items"]
    items[name] = {"count": count, "description": description}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add")
    args = parser.parse_args()
    db = load_db()
    if args.cmd == "add":
        add_item(db, "sample")
    save_db(db)


if __name__ == "__main__":
    main()
""",
)


def test_goal_wants_runnable_german_console_project() -> None:
    goal = "schreib ein python projekt, das über die konsole läuft"
    assert goal_wants_runnable_script(goal)


def test_stub_inventory_has_gaps() -> None:
    goal = "schreib ein python projekt, das über die konsole läuft"
    gaps = find_impl_gaps(STUB_INVENTORY, goal, path="inventory.py")
    assert any("add_item" in gap for gap in gaps)
    assert any("entry point" in gap.lower() for gap in gaps)


def test_complete_cli_has_no_gaps() -> None:
    goal = "schreib ein python projekt, das über die konsole läuft"
    gaps = find_impl_gaps(COMPLETE_CLI, goal, path="inventory.py")
    assert gaps == []


def test_cpp_entry_point_is_language_specific() -> None:
    goal = "schreib ein console tool"
    missing = find_impl_gaps("void helper() {}\n", goal, path="tool.cpp")
    assert any("int main" in gap for gap in missing)
    present = find_impl_gaps("int main() { return 0; }\n", goal, path="tool.cpp")
    assert present == []
    status = summarize_impl_status("int main() { return 0; }\n", goal, path="tool.cpp")
    assert "int main(...)" in status
    assert "present" in status


def test_goal_text_selects_cpp_entry_without_path() -> None:
    from mango_agent.impl_completeness import detect_language, expected_entry_label
    from mango_agent.work_plan import build_work_plan

    goal = "schreib ein c++ console tool"
    assert detect_language(goal=goal) == "cpp"
    assert "int main" in expected_entry_label(goal=goal)
    # Work plan stays language-agnostic — no hardcoded entry snippets.
    plan = build_work_plan(goal)
    assert "write_file" in plan
    assert "int main" not in plan
    assert "__main__" not in plan


def test_agent_blocks_finish_on_incomplete_greenfield_cli(tmp_path: Path) -> None:
    import json

    target = tmp_path / "inventory.py"
    write = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": STUB_INVENTORY})}>'
    )
    runner = FakeModelRunner([write, "Fertig. Das CLI-Projekt ist implementiert."])
    agent = Agent(
        runner,
        max_iterations=4,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    result = agent.run("Schreib ein Python-Projekt, das über die Konsole läuft.")
    assert result.stop_reason != StopReason.COMPLETED
    assert agent._impl_gaps


def test_refresh_clears_gaps_via_transition_not_hardcoded_main(tmp_path: Path) -> None:
    """Closing gaps emits impl_complete from the resolved list — not a __main__ string match."""
    from mango_context import ContextEngine

    goal = "Schreib ein console tool."
    path = tmp_path / "tool.cpp"
    path.write_text("void helper() {}\n", encoding="utf-8")
    agent = Agent(
        FakeModelRunner([]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = goal
    agent._cli_goal = True
    agent._require_tools = True
    engine = ContextEngine(goal=goal)

    agent._refresh_impl_completeness(engine)
    assert agent._impl_gaps
    assert any("int main" in gap for gap in agent._impl_gaps)
    assert "NOT finished" in (engine.state.verification_feedback or "")
    open_gaps = list(agent._impl_gaps)

    path.write_text("int main() { return 0; }\n", encoding="utf-8")
    agent._refresh_impl_completeness(engine)
    assert agent._impl_gaps == []
    feedback = engine.state.verification_feedback or ""
    assert "now closed" in feedback.lower() or "do NOT re-apply" in feedback
    assert "NOT finished" not in feedback
    # Resolved list is dynamic — whatever was open, including int main(...).
    assert any(gap.split(": ", 1)[-1] in feedback for gap in open_gaps)
    assert "int main" in (engine.state.impl_status or "")
    assert "present" in (engine.state.impl_status or "")


HOLLOW_DISCORD_BOT = """\
import discord
import aiohttp
import os

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")


class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents())

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

    #
"""

DISCORD_GOAL = (
    "Create a Discord bot in Python that waits for messages in a channel, "
    "sends each message as a prompt to the LM Studio API "
    "(localhost OpenAI-compatible GPT-style API), waits for the output, "
    "and posts the output back to Discord as a new message."
)


def test_hollow_discord_bot_is_not_complete() -> None:
    from mango_agent.impl_completeness import looks_truncated_source, required_features

    assert looks_truncated_source(HOLLOW_DISCORD_BOT)
    assert goal_wants_runnable_script(DISCORD_GOAL)
    features = required_features(DISCORD_GOAL)
    assert any("HTTP" in f or "API" in f for f in features)
    assert any("send" in f.lower() or "reply" in f.lower() for f in features)

    gaps = find_impl_gaps(HOLLOW_DISCORD_BOT, DISCORD_GOAL, path="bot.py")
    blob = "\n".join(gaps).lower()
    assert "truncated" in blob
    assert "on_message" in blob or "incomplete" in blob
    assert "http" in blob or "api" in blob
    assert "send" in blob or "reply" in blob


def test_complete_http_handler_clears_hollow_gaps() -> None:
    complete = '''\
import discord
import aiohttp
import os

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")


class Bot(discord.Client):
    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        async with aiohttp.ClientSession() as session:
            async with session.post(LM_STUDIO_URL, json={"messages": [{"role": "user", "content": message.content}]}) as resp:
                data = await resp.json()
        reply = data["choices"][0]["message"]["content"]
        await message.channel.send(reply)


if __name__ == "__main__":
    Bot().run(os.environ["DISCORD_BOT_TOKEN"])
'''
    gaps = find_impl_gaps(complete, DISCORD_GOAL, path="bot.py")
    assert gaps == []


def test_agent_blocks_finish_on_hollow_discord_bot(tmp_path: Path) -> None:
    from mango_context import ContextEngine

    target = tmp_path / "bot.py"
    target.write_text(HOLLOW_DISCORD_BOT, encoding="utf-8")
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=2,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = DISCORD_GOAL
    agent._acted_once = True
    agent._require_tools = True
    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._refresh_impl_completeness(engine)
    assert agent._impl_gaps
    assert not agent._finish_allowed()
    assert agent._logic_gaps()
    assert agent._forced_tool_name() == "insert_lines"
    assert not agent._inventory_style_goal(DISCORD_GOAL)


def test_discord_does_not_get_inventory_skeleton_token_cap(tmp_path: Path) -> None:
    """Discord is _cli_goal (runnable) but must NOT inherit the 1024 skeleton write cap."""
    from mango_agent.agent import _CLI_SKELETON_WRITE_MAX_TOKENS, _WRITE_TOOL_MAX_TOKENS

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
    assert agent._cli_goal
    assert not agent._inventory_cli_budget()
    # Simulate run() budget selection for non-inventory runnable goals.
    if agent._inventory_cli_budget():
        agent._write_tool_max_tokens = _CLI_SKELETON_WRITE_MAX_TOKENS
    else:
        agent._write_tool_max_tokens = _WRITE_TOOL_MAX_TOKENS
    assert agent._write_tool_max_tokens == _WRITE_TOOL_MAX_TOKENS
    assert agent._write_tool_max_tokens > _CLI_SKELETON_WRITE_MAX_TOKENS


def test_logic_gaps_grammar_excludes_edit_file(tmp_path: Path) -> None:
    target = tmp_path / "discord_bot.py"
    target.write_text(HOLLOW_DISCORD_BOT, encoding="utf-8")
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
    agent._acted_once = True
    agent._require_tools = True
    agent._prefer_insert_lines = True
    from mango_context import ContextEngine

    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._refresh_impl_completeness(engine)
    assert agent._forced_tool_name() == "insert_lines"
    filtered = agent._apply_grammar_filters(list(agent._enabled_registry_names()))
    assert filtered == ["insert_lines"]


def test_logic_gaps_force_insert_not_micro_edit(tmp_path: Path) -> None:
    """After a skeleton write, Discord bots must insert missing logic — not ±3-line edits."""
    from mango_agent.prompt import feedback
    from mango_context import ContextEngine

    target = tmp_path / "discord_bot.py"
    target.write_text(HOLLOW_DISCORD_BOT, encoding="utf-8")
    agent = Agent(
        FakeModelRunner(["done"]),
        max_iterations=3,
        verification_root=tmp_path,
        require_tools=True,
        task_wants_tests=False,
        tool_registry=create_default_registry(),
    )
    agent._task = DISCORD_GOAL
    agent._cli_goal = True
    agent._require_tools = True
    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._refresh_impl_completeness(engine)
    logic = agent._logic_gaps()
    assert logic
    assert agent._forced_tool_name() == "insert_lines"
    engine.set_verification_feedback(
        feedback(
            "impl_logic_missing",
            gaps="\n".join(f"- {g}" for g in logic[:8]),
            path="discord_bot.py",
            line="19",
        )
    )
    fb = engine.state.verification_feedback or ""
    assert "insert_lines" in fb.lower()
    assert "do not" in fb.lower() and "edit_file" in fb.lower()


def test_nibble_edit_blocked_and_reverted(tmp_path: Path) -> None:
    from mango_tools.types import ToolCall, ToolResult

    target = tmp_path / "discord_bot.py"
    original = HOLLOW_DISCORD_BOT
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
    from mango_context import ContextEngine

    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._refresh_impl_completeness(engine)
    assert agent._logic_gaps()

    call = ToolCall(
        name="edit_file",
        arguments={
            "path": str(target),
            "old_string": "return",
            "new_string": "return  # noop",
        },
        raw="",
        start=0,
        end=0,
    )
    reason = agent._logic_gap_block_reason(call)
    assert reason and "insert_lines" in reason.lower()

    snaps = {str(target.resolve()): original}
    target.write_text(original + "x = 1\n", encoding="utf-8")
    tiny = ToolResult(
        success=True,
        tool_name="insert_lines",
        output={"path": str(target), "lines_inserted": 1},
        call=ToolCall(
            name="insert_lines",
            arguments={"path": str(target), "line": 99, "content": "x = 1\n"},
            raw="",
            start=0,
            end=0,
        ),
    )
    out = agent._reject_nibble_mutations([tiny], snaps)
    assert len(out) == 1
    assert out[0].success is False
    assert target.read_text(encoding="utf-8") == original


def test_substantial_insert_addresses_gaps_kept(tmp_path: Path) -> None:
    from mango_tools.types import ToolCall, ToolResult

    target = tmp_path / "discord_bot.py"
    original = HOLLOW_DISCORD_BOT
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
    from mango_context import ContextEngine

    engine = ContextEngine(goal=DISCORD_GOAL)
    agent._refresh_impl_completeness(engine)
    block = (
        "    payload = {'messages': [{'role': 'user', 'content': message.content}]}\n"
        "    resp = requests.post('http://localhost:1234/v1/chat/completions', json=payload)\n"
        "    text = resp.json()['choices'][0]['message']['content']\n"
        "    await message.channel.send(text)\n"
        "\n"
        "\nif __name__ == '__main__':\n"
        "    bot.run(TOKEN)\n"
    )
    snaps = {str(target.resolve()): original}
    kept = ToolResult(
        success=True,
        tool_name="insert_lines",
        output={"path": str(target), "lines_inserted": 8},
        call=ToolCall(
            name="insert_lines",
            arguments={"path": str(target), "line": 19, "content": block},
            raw="",
            start=0,
            end=0,
        ),
    )
    out = agent._reject_nibble_mutations([kept], snaps)
    assert out[0].success is True
