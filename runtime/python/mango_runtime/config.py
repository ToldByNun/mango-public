from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from mango_runtime.types import RuntimeConfig

DEFAULT_CONFIG_NAMES = ("config.yaml", "config.yml")


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()

    env_path = os.environ.get("MANGO_RUNTIME_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()

    runtime_root = Path(__file__).resolve().parents[2]
    for name in DEFAULT_CONFIG_NAMES:
        candidate = runtime_root / name
        if candidate.is_file():
            return candidate

    return runtime_root / "config.yaml"


def config_to_dict(config: RuntimeConfig) -> dict[str, Any]:
    return {
        "model": {
            "path": config.model.path,
            "n_ctx": config.model.n_ctx,
            "n_batch": config.model.n_batch,
            "n_ubatch": config.model.n_ubatch,
        },
        "hardware": {
            "n_gpu_layers": config.hardware.n_gpu_layers,
            "n_threads": config.hardware.n_threads,
        },
        "inference": {
            "max_tokens": config.inference.max_tokens,
            "temperature": config.inference.temperature,
            "top_p": config.inference.top_p,
            "stop": list(config.inference.stop),
            "repeat_penalty": config.inference.repeat_penalty,
            "repeat_last_n": config.inference.repeat_last_n,
        },
    }


def load_config_file(path: str | Path, *, require_model: bool = True) -> RuntimeConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Runtime config not found: {config_path}. "
            "Copy config.example.yaml to config.yaml and set model.path."
        )

    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    config = RuntimeConfig.from_dict(data)

    env_model_path = os.environ.get("MANGO_GGUF_MODEL_PATH")
    if env_model_path:
        config = RuntimeConfig(
            model=config.model.__class__(
                path=env_model_path,
                n_ctx=config.model.n_ctx,
                n_batch=config.model.n_batch,
                n_ubatch=config.model.n_ubatch,
            ),
            hardware=config.hardware,
            inference=config.inference,
        )

    if require_model and not config.model.path:
        raise ValueError(
            "model.path is empty. Set it in config.yaml or MANGO_GGUF_MODEL_PATH."
        )

    return config


def load_config(path: str | Path | None = None) -> RuntimeConfig:
    return load_config_file(resolve_config_path(path), require_model=True)


def save_config(path: str | Path, config: RuntimeConfig) -> None:
    config_path = Path(path).expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config_to_dict(config)
    text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    tmp = config_path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(config_path)

