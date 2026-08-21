from __future__ import annotations

import os
from pathlib import Path

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


def load_config(path: str | Path | None = None) -> RuntimeConfig:
    config_path = resolve_config_path(path)
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
            ),
            hardware=config.hardware,
            inference=config.inference,
        )

    if not config.model.path:
        raise ValueError(
            "model.path is empty. Set it in config.yaml or MANGO_GGUF_MODEL_PATH."
        )

    return config
