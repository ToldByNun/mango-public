"""Live AgentBridge E2E: slim-prompt Discord-bot goal — no epistemic soft-lock."""
from __future__ import annotations

import json
import tempfile
import time
from collections import Counter
from pathlib import Path

from mango_cli.agent_bridge import AgentBridge

GOAL = (
    "Create a Discord bot in Python that waits for messages in a channel, "
    "sends each message as a prompt to the LM Studio API "
    "(localhost OpenAI-compatible GPT-style API), waits for the output, "
    "and posts the output back to Discord as a new message."
)


def main() -> int:
    ws = Path(tempfile.mkdtemp(prefix="discord_live_"))
    cfg = Path(r"C:\Users\mikaj\Desktop\DevDeck\runtime\config.yaml")
    print("workspace", ws, flush=True)

    tools: list[str] = []
    prompts: list[int] = []

    def on_event(ev: dict) -> None:
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        name = str(data.get("name") or data.get("tool") or "")
        if name:
            tools.append(name)
            print(f"TOOL {name}", flush=True)
        # Capture prompt size hints from mango logs if present in text events.
        text = str(data.get("text") or "")
        if "prompt_chars=" in text:
            try:
                n = int(text.split("prompt_chars=", 1)[1].split()[0])
                prompts.append(n)
            except ValueError:
                pass

    bridge = AgentBridge(config_path=cfg, workspace=ws, session_id="discord-live1")
    bridge.attach_event_handler(on_event)
    print("loading...", flush=True)
    bridge.load()
    print("model", bridge.model_path, flush=True)

    t0 = time.time()
    result = bridge.run(GOAL, mode="")
    elapsed = time.time() - t0

    stop = getattr(result, "stop_reason", None)
    err = getattr(result, "error", None)
    metrics = getattr(result, "metrics", None)
    by_name = dict(getattr(metrics, "tool_calls_by_name", None) or {})
    if by_name:
        counts = Counter(by_name)
        # Expand counts into a flat list for thrash checks below.
        tools = [name for name, n in by_name.items() for _ in range(int(n))]
    else:
        counts = Counter(tools)

    print("STOP", stop, flush=True)
    print("ERROR", err, flush=True)
    print("ELAPSED_S", round(elapsed, 1), flush=True)
    print("TOOL_COUNTS", dict(counts), flush=True)
    print("FINAL_PROMPT_CHARS", getattr(metrics, "final_prompt_chars", None), flush=True)
    py = sorted(p.name for p in ws.rglob("*.py") if p.is_file())
    print("PY_FILES", py, flush=True)
    if prompts:
        print("PROMPT_CHARS_MAX", max(prompts), flush=True)

    # Soft-lock detection: endless ask_epistemic / codebase_lookup without writes.
    writes = counts.get("write_file", 0) + counts.get("edit_file", 0)
    lookups = (
        counts.get("ask_epistemic", 0)
        + counts.get("codebase_lookup", 0)
        + counts.get("research_codebase", 0)
    )
    # Coding-discipline metrics (Agent Coding Discipline plan).
    edit_n = int(counts.get("edit_file", 0) or 0)
    read_n = int(counts.get("read_file", 0) or 0)
    insert_n = int(counts.get("insert_lines", 0) or 0)
    print(
        "DISCIPLINE",
        {
            "edit_file": edit_n,
            "read_file": read_n,
            "insert_lines": insert_n,
            "write_file": int(counts.get("write_file", 0) or 0),
            "stop": str(stop),
        },
        flush=True,
    )
    if edit_n > 0:
        print("WARN edit_file used (prefer insert_lines/write_file)", edit_n, flush=True)
    if read_n > 4:
        print("WARN read_file thrash", read_n, flush=True)

    bot = next((ws / name for name in py if "discord" in name.lower() or name == "bot.py"), None)
    if bot is None and py:
        bot = ws / py[0]
    if bot is not None and bot.is_file():
        src = bot.read_text(encoding="utf-8", errors="replace")
        compile_ok = True
        try:
            compile(src, str(bot), "exec")
        except SyntaxError as exc:
            compile_ok = False
            print("FAIL syntax", exc, flush=True)
            return 6
        has_http = any(tok in src for tok in ("requests.", "httpx.", "/v1/chat", "aiohttp"))
        has_send = any(tok in src for tok in (".send(", ".reply("))
        has_run = "bot.run(" in src or "client.run(" in src
        print(
            "BOT_CHECKS",
            {"compile": compile_ok, "http": has_http, "send": has_send, "run": has_run},
            flush=True,
        )
        if not (has_http and has_send and has_run):
            print("FAIL hollow bot (missing http/send/run)", flush=True)
            return 7

    if lookups >= 6 and writes == 0:
        print("FAIL epistemic soft-lock", lookups, flush=True)
        return 2
    if counts.get("ask_epistemic", 0) > 4:
        print("FAIL ask_epistemic thrash", counts.get("ask_epistemic"), flush=True)
        return 3
    if not py:
        print("FAIL no python files written", flush=True)
        return 4
    if writes == 0 and not py:
        print("FAIL never wrote a file", flush=True)
        return 5
    # Files on disk prove progress even if the event stream missed tool chips.
    if writes == 0 and py:
        writes = len(py)

    print("OK_DISCORD_PROGRESS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
