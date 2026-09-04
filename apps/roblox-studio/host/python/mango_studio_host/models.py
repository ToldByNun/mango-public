"""Discover local GGUF models (mirrors Electron listGgufModels)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_MAX_DEPTH = 5
_MAX_MODELS = 200

_BRAND_NAMES = {
    "gemma": "Gemma",
    "codegemma": "CodeGemma",
    "qwen": "Qwen",
    "qwen2": "Qwen2",
    "qwen2.5": "Qwen2.5",
    "qwq": "QwQ",
    "llama": "Llama",
    "codellama": "CodeLlama",
    "tinyllama": "TinyLlama",
    "mistral": "Mistral",
    "mixtral": "Mixtral",
    "ministral": "Ministral",
    "codestral": "Codestral",
    "devstral": "Devstral",
    "phi": "Phi",
    "deepseek": "DeepSeek",
    "grok": "Grok",
    "yi": "Yi",
    "glm": "GLM",
    "chatglm": "ChatGLM",
    "kimi": "Kimi",
    "olmo": "OLMo",
    "granite": "Granite",
    "starcoder": "StarCoder",
    "starcoder2": "StarCoder2",
    "nemotron": "Nemotron",
    "nvidia": "NVIDIA",
    "mango": "Mango",
}

_QUANT_RE = re.compile(r"\b(Q[0-9]_[A-Z_]+|[IF]Q[0-9S]_[A-Z0-9]+|[IF]\d{1,2})\b", re.I)
_SIZE_RE = re.compile(r"\b(\d+(\.\d+)?[BMK])\b", re.I)


def format_model_label(raw: str) -> str:
    parts = re.split(r"[-_\s]+", raw.replace(".gguf", ""))
    out: list[str] = []
    quant = ""
    size = ""
    for p in parts:
        if not p:
            continue
        lower = p.lower()
        if _QUANT_RE.search(p):
            quant = p.upper().replace(" ", "_")
            continue
        size_match = _SIZE_RE.search(p)
        if size_match and lower not in _BRAND_NAMES:
            size = size_match.group(1).upper()
            continue
        brand = _BRAND_NAMES.get(lower)
        if brand:
            out.append(brand)
        elif p[0].isdigit():
            out.append(p)
        else:
            out.append(p[:1].upper() + p[1:])
    label = " ".join(out)
    suffix = " ".join(x for x in (size, quant) if x)
    return f"{label} {suffix}".strip() if suffix else label


def _discover_roots(repo_root: Path | None = None) -> list[Path]:
    home = Path.home()
    candidates = [
        home / ".cache" / "lm-studio" / "models",
        home / ".lmstudio" / "models",
        home / ".ollama" / "models",
        home / "AppData" / "Local" / "lm-studio" / "models",
        home / "AppData" / "Local" / "nomic.ai" / "GPT4All",
        home / "models",
        home / "Downloads",
        home / ".mango" / "models",
    ]
    if repo_root is not None:
        candidates.append(repo_root / "training" / "output")
        candidates.append(repo_root / "models")
    return [p for p in candidates if p.is_dir()]


def _walk_gguf(root: Path, depth: int, out: list[dict[str, str]]) -> None:
    if depth > _MAX_DEPTH or len(out) >= _MAX_MODELS:
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if len(out) >= _MAX_MODELS:
            break
        try:
            if entry.is_dir():
                _walk_gguf(entry, depth + 1, out)
                continue
        except OSError:
            continue
        if not entry.name.lower().endswith(".gguf"):
            continue
        out.append(
            {
                "path": str(entry.resolve()),
                "label": format_model_label(entry.stem),
            }
        )


def list_gguf_models(repo_root: Path | None = None) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for root in _discover_roots(repo_root):
        _walk_gguf(root, 0, found)
    unique: list[dict[str, str]] = []
    for item in found:
        key = item["path"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda m: m["label"].lower())
    return unique
