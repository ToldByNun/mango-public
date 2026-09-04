from __future__ import annotations

from mango_agent.thinking import normalize_thinking_level, thinking_preset, verify_hint_for


def test_normalize_thinking_level() -> None:
    assert normalize_thinking_level(None) == "off"
    assert normalize_thinking_level("DEEP") == "deep"
    assert normalize_thinking_level("nope") == "off"


def test_thinking_preset_mapping() -> None:
    assert thinking_preset("off").chain_steps == 0
    assert thinking_preset("off").max_reasoning_cycles == 0
    assert thinking_preset("off").thought_max_tokens == 128
    assert thinking_preset("think").chain_steps == 2
    assert thinking_preset("think").max_reasoning_cycles == 3
    assert thinking_preset("think").thought_max_tokens == 256
    assert thinking_preset("deep").chain_steps == 3
    assert thinking_preset("deep").verify_strength == 2
    assert thinking_preset("deep").thought_max_tokens == 384
    assert thinking_preset("deep").summary_max_tokens == 420
    assert thinking_preset("max").chain_steps == 3
    assert thinking_preset("max").max_reasoning_cycles == 6
    assert thinking_preset("max").thought_max_tokens == 512
    assert thinking_preset("max").cot_extended == 512


def test_verify_hint_scales() -> None:
    assert verify_hint_for(0) == ""
    assert "Soft" in verify_hint_for(1) or "inspect" in verify_hint_for(1).lower()
    assert "blocked" in verify_hint_for(1).lower() or "assume" in verify_hint_for(1).lower()
    assert "Verify" in verify_hint_for(2) or "verify" in verify_hint_for(2).lower()
    assert "Strict" in verify_hint_for(3) or "Verify again" in verify_hint_for(3)
