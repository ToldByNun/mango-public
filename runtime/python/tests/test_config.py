from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from mango_runtime.config import load_config
from mango_runtime.gguf_loader import GGUFLoader, GGUFLoadError


def test_load_config_from_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "model": {"path": "models/test.gguf", "n_ctx": 2048},
                "hardware": {"n_gpu_layers": -1, "n_threads": 4},
                "inference": {"max_tokens": 128, "temperature": 0.5},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_file)
    assert config.model.path == "models/test.gguf"
    assert config.model.n_ctx == 2048
    assert config.hardware.n_gpu_layers == -1
    assert config.hardware.n_threads == 4
    assert config.inference.max_tokens == 128
    assert config.inference.temperature == 0.5


def test_env_model_path_overrides_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump({"model": {"path": "old.gguf"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MANGO_GGUF_MODEL_PATH", str(tmp_path / "override.gguf"))

    config = load_config(config_file)
    assert config.model.path == str(tmp_path / "override.gguf")


def test_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")


def test_empty_model_path_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"model": {"path": ""}}), encoding="utf-8")

    with pytest.raises(ValueError, match="model.path is empty"):
        load_config(config_file)


def test_gguf_loader_rejects_missing_file(tmp_path: Path) -> None:
    from mango_runtime.types import ModelConfig, RuntimeConfig

    loader = GGUFLoader(RuntimeConfig(model=ModelConfig(path=str(tmp_path / "nope.gguf"))))
    with pytest.raises(GGUFLoadError, match="not found"):
        loader.validate()


def test_gguf_loader_rejects_wrong_extension(tmp_path: Path) -> None:
    from mango_runtime.types import ModelConfig, RuntimeConfig

    bad_file = tmp_path / "model.bin"
    bad_file.write_text("fake", encoding="utf-8")
    loader = GGUFLoader(RuntimeConfig(model=ModelConfig(path=str(bad_file))))
    with pytest.raises(GGUFLoadError, match="Expected a .gguf"):
        loader.validate()


def test_llama_kwargs_use_windowed_swa_cache(tmp_path: Path) -> None:
    from mango_runtime.types import ModelConfig, RuntimeConfig

    gguf = tmp_path / "gemma4.gguf"
    gguf.write_bytes(b"GGUF")
    loader = GGUFLoader(RuntimeConfig(model=ModelConfig(path=str(gguf), n_ctx=16384, n_batch=512)))
    kwargs = loader.llama_kwargs()
    assert kwargs["swa_full"] is False
    assert kwargs["type_k"] == 8
    assert kwargs["type_v"] == 8
    assert kwargs["n_ctx"] == 16384
