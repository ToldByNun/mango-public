from __future__ import annotations

import os

from mango_agent.agent import _parse_libraries
from mango_tools.confirm_gate import request_confirm, resolve_confirm, set_confirm_emitter
from mango_tools.implementations import create_default_registry


def test_parse_libraries_caps_and_strips_junk() -> None:
    raw = (
        "discord.py, aiohttp, requests, httpx, openai, tenacity, pydantic, "
        "rich-click, rich-click, rich-, dotenv"
    )
    names = _parse_libraries(raw)
    assert names == ["discord", "aiohttp", "requests", "httpx", "openai"]
    assert _parse_libraries("dotenv, rich-") == ["python-dotenv"]
    assert _parse_libraries("httpx, httpx, HTTPX, discord.py, discord") == ["httpx", "discord"]


def test_builtin_registry_has_install_and_web() -> None:
    reg = create_default_registry()
    assert reg.has("install_packages")
    assert reg.has("fetch_url")
    assert reg.has("web_research")


def test_confirm_gate_auto_env(monkeypatch) -> None:
    set_confirm_emitter(None)
    monkeypatch.setenv("MANGO_AUTO_CONFIRM", "1")
    assert request_confirm(summary="test", kind="shell", detail="echo hi") is True
    monkeypatch.delenv("MANGO_AUTO_CONFIRM", raising=False)
    assert request_confirm(summary="test", kind="shell") is False


def test_confirm_gate_resolve() -> None:
    seen: list[tuple[str, dict]] = []

    def emit(event: str, payload: dict) -> None:
        seen.append((event, payload))
        resolve_confirm(str(payload["request_id"]), True)

    set_confirm_emitter(emit)
    try:
        assert request_confirm(summary="pip install httpx", kind="pip") is True
        assert seen and seen[0][0] == "agent.confirm"
    finally:
        set_confirm_emitter(None)


def test_bind_task_prompt_requires_install_and_permission() -> None:
    from mango_tools.implementations.bind_task_prompt import bind_task_prompt, validate_task_prompt

    assert validate_task_prompt("just write code")["ok"] is False
    assert validate_task_prompt("MUST install_packages silently")["ok"] is False
    ok = validate_task_prompt(
        "MUST call install_packages for missing libs; wait for user confirm popup."
    )
    assert ok["ok"] is True
    stored: list[str] = []

    def store(text: str, libs: list[str] | None = None) -> None:
        stored.append(text)

    result = bind_task_prompt(
        "<task_lock>MUST install_packages after confirm popup before write_file.</task_lock>",
        libs="discord, httpx",
        _context={"_bind_task_prompt": store},
    )
    assert result["ok"] is True
    assert stored and "install_packages" in stored[0]
    assert "discord" in stored[0]


def test_bootstrap_sole_tool_phases() -> None:
    from mango_agent.agent import Agent, _BOOTSTRAP_SOLE_TOOL

    assert _BOOTSTRAP_SOLE_TOOL == {
        "declare": "declare_apis",
        "epistemic": "ask_epistemic",
        "install": "install_packages",
    }

    class _FakeModel:
        pass

    agent = Agent(_FakeModel(), require_tools=True, plan_apis_first=True, enable_declare_apis=True)
    agent._task = "Discord bot with aiohttp"
    agent._apis_declared_once = False
    assert agent._plan_gate_phase() == "declare"
    assert agent._forced_tool_name() == "declare_apis"

    agent._apis_declared_once = True
    agent._declared_libraries = ["discord", "aiohttp"]
    agent._epistemic_once = False
    assert agent._plan_gate_phase() == "epistemic"
    assert agent._forced_tool_name() == "ask_epistemic"

    agent._epistemic_once = True
    agent._install_resolved = False

    # Force missing imports path without real packages.
    agent._libs_missing_import = lambda: ["discord", "aiohttp"]  # type: ignore[method-assign]
    assert agent._plan_gate_phase() == "install"
    assert agent._forced_tool_name() == "install_packages"

    agent._install_resolved = True
    assert agent._plan_gate_phase() is None
    # After gate: create goal may force write_file
    agent._greenfield_run = True
    agent._prefer_write_file = True
    names = agent._action_tool_names()
    assert "write_file" in names
    assert names == ["write_file"] or names[0] == "write_file" or "declare_apis" not in names[:1]
