"""Discord quality gaps must catch real broken bot wiring, not just token presence."""

from __future__ import annotations

from pathlib import Path

from mango_agent.impl_completeness import find_impl_gaps

DISCORD_GOAL = (
    "Create a Discord bot in Python that waits for messages in a channel, "
    "sends each message as a prompt to the LM Studio API "
    "(localhost OpenAI-compatible GPT-style API), waits for the output, "
    "and posts the output back to Discord as a new message."
)

# Exact failure mode from live run discord_live_qcmv1xe5 (mashed + sync send).
BAD_LIVE_SOURCE = """\
# impl.py — Discord bot that forwards channel messages to LM Studio and posts the reply.

import discord
import requests
import os

# ── Configuration ──────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234")
LM_STUDIO_KEY = os.environ.get("LM_STUDIO_KEY", "")
MODEL_NAME = os.environ.get("MODEL_NAME", "local")

# ── Discord client ─────────────────────────────────────────# --- Discord bot: wait for messages, call LM Studio (OpenAI-compatible), post reply ---
import os
import discord
import requests

# LM Studio OpenAI-compatible endpoint (localhost)
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
LM_STUDIO_KEY = os.getenv("LM_STUDIO_KEY", "lm-studio")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))


def call_lm_studio(prompt: str) -> str:
    payload = {"model": "local", "messages": [{"role": "user", "content": prompt}]}
    headers = {"Authorization": f"Bearer {LM_STUDIO_KEY}", "Content-Type": "application/json"}
    resp = requests.post(LM_STUDIO_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def send_message(channel, text: str) -> None:
    channel.send(text).add_done_callback(lambda _f: None)


def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    if message.channel.id != CHANNEL_ID:
        return
    prompt = message.content
    if not prompt:
        return
    try:
        reply_text = call_lm_studio(prompt)
    except Exception as exc:
        print(f"LM Studio call failed: {exc}")
        return
    send_message(message.channel, reply_text)


def main() -> None:
    bot = discord.Client(intents=discord.Intents.default())

    @bot.event
    async def on_ready():
        print("Bot is online and ready.")

    bot.on_message = on_message
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
"""

GOOD_SOURCE = """\
import os
import discord
import requests

TOKEN = os.environ.get("DISCORD_TOKEN", "")
LM_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)


def call_lm_studio(prompt: str) -> str:
    payload = {"model": "local", "messages": [{"role": "user", "content": prompt}]}
    resp = requests.post(LM_URL, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    reply = call_lm_studio(message.content)
    await message.channel.send(reply)


if __name__ == "__main__":
    bot.run(TOKEN)
"""


def test_bad_live_source_has_real_quality_gaps() -> None:
    gaps = find_impl_gaps(BAD_LIVE_SOURCE, DISCORD_GOAL, path="impl.py")
    blob = " | ".join(gaps).lower()
    assert "mashed" in blob or "duplicate" in blob
    assert "async" in blob
    assert "await" in blob or "add_done_callback" in blob
    assert "message_content" in blob


def test_good_discord_source_has_no_gaps() -> None:
    gaps = find_impl_gaps(GOOD_SOURCE, DISCORD_GOAL, path="discord_bot.py")
    assert gaps == []


def test_superficial_send_without_await_still_gaps() -> None:
    # Old harness only checked for ".send(" — that must no longer be enough.
    shallow = """\
import discord
import requests
import os

bot = discord.Client(intents=discord.Intents.default())

def call_lm(p):
    return requests.post('http://localhost:1234/v1/chat/completions', json={}).json()

def on_message(message):
    if message.author.bot:
        return
    text = call_lm(message.content)
    message.channel.send(text)

bot.run(os.environ['DISCORD_TOKEN'])
if __name__ == '__main__':
    pass
"""
    gaps = find_impl_gaps(shallow, DISCORD_GOAL, path="bot.py")
    assert gaps
    assert any("await" in g.lower() or "async" in g.lower() for g in gaps)


def test_auto_heal_message_content_intent() -> None:
    from mango_agent.impl_completeness import try_auto_add_message_content_intent

    src = """\
import discord
import requests
import os

bot = discord.Client(intents=discord.Intents.default())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    r = requests.post('http://localhost:1234/v1/chat/completions', json={'messages':[{'role':'user','content':message.content}]})
    await message.channel.send(r.json()['choices'][0]['message']['content'])

if __name__ == '__main__':
    bot.run(os.environ['DISCORD_TOKEN'])
"""
    gaps = find_impl_gaps(src, DISCORD_GOAL, path="bot.py")
    assert any("message_content" in g for g in gaps)
    healed = try_auto_add_message_content_intent(src, DISCORD_GOAL, path="bot.py")
    assert healed is not None
    assert "message_content = True" in healed
    assert find_impl_gaps(healed, DISCORD_GOAL, path="bot.py") == []


def test_bogus_intents_default_message_content_is_gap() -> None:
    """String presence is not enough — Intents.default.message_content is invalid."""
    from mango_agent.impl_completeness import try_auto_add_message_content_intent

    src = """\
import discord
import requests
import os

bot = discord.Client(intents=discord.Intents.default())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    r = requests.post('http://localhost:1234/v1/chat/completions', json={'messages':[{'role':'user','content':message.content}]})
    await message.channel.send(r.json()['choices'][0]['message']['content'])

if __name__ == '__main__':
    bot.run(os.environ['DISCORD_TOKEN'])
discord.Intents.default.message_content = True
"""
    gaps = find_impl_gaps(src, DISCORD_GOAL, path="bot.py")
    assert any("message_content" in g for g in gaps)
    healed = try_auto_add_message_content_intent(src, DISCORD_GOAL, path="bot.py")
    assert healed is not None
    assert "Intents.default.message_content" not in healed
    assert "_intents.message_content = True" in healed
    assert "Client(intents=_intents)" in healed
    assert find_impl_gaps(healed, DISCORD_GOAL, path="bot.py") == []


def test_agent_auto_heals_message_content_after_write(tmp_path: Path) -> None:
    """After write, sole message_content gap must be healed — not insert-thrashed."""
    from mango_agent import Agent
    from mango_context import ContextEngine
    from mango_tools import create_default_registry
    from test_agent_loop import FakeModelRunner

    target = tmp_path / "impl.py"
    almost = """\
import discord
import requests
import os

bot = discord.Client(intents=discord.Intents.default())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    r = requests.post('http://localhost:1234/v1/chat/completions', json={'messages':[{'role':'user','content':message.content}]})
    await message.channel.send(r.json()['choices'][0]['message']['content'])

if __name__ == '__main__':
    bot.run(os.environ['DISCORD_TOKEN'])
"""
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
    engine = ContextEngine(goal=DISCORD_GOAL)
    target.write_text(almost, encoding="utf-8")
    agent._refresh_impl_completeness(engine)
    assert agent._impl_gaps
    assert all("message_content" in str(g).lower() for g in agent._impl_gaps)
    assert agent._auto_heal_missing_entry_points(engine)
    healed = target.read_text(encoding="utf-8")
    assert "_intents.message_content = True" in healed
    assert find_impl_gaps(healed, DISCORD_GOAL, path="impl.py") == []


def test_mash_insert_rejected(tmp_path: Path) -> None:
    from mango_agent import Agent
    from mango_context import ContextEngine
    from mango_tools import create_default_registry
    from mango_tools.types import ToolCall, ToolResult
    from test_agent_loop import FakeModelRunner

    target = tmp_path / "impl.py"
    good_head = GOOD_SOURCE
    target.write_text(good_head, encoding="utf-8")
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
    agent._refresh_impl_completeness(engine)
    second = (
        "\n# --- second copy ---\n"
        "import discord\nimport requests\nimport os\n"
        "bot = discord.Client(intents=discord.Intents.default())\n"
        "@bot.event\n"
        "async def on_message(message):\n"
        "    await message.channel.send('x')\n"
        "bot.run('t')\n"
    )
    snaps = {str(target.resolve()): good_head}
    target.write_text(good_head + second, encoding="utf-8")
    call = ToolCall(
        name="insert_lines",
        arguments={"path": str(target), "line": 99, "content": second},
        raw="",
        start=0,
        end=0,
    )
    result = ToolResult(
        success=True,
        tool_name="insert_lines",
        output={"path": str(target), "lines_inserted": 10},
        call=call,
    )
    out = agent._reject_nibble_mutations([result], snaps)
    assert out[0].success is False
    assert out[0].metadata.get("mash_rejected") is True
    assert target.read_text(encoding="utf-8") == good_head
    assert agent._prefer_write_file is True
