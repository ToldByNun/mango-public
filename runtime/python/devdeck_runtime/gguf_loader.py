from __future__ import annotations

from pathlib import Path

from devdeck_runtime.types import HardwareConfig, ModelConfig, RuntimeConfig


class GGUFLoadError(Exception):
    pass


class GGUFLoader:
    """Validates GGUF paths and builds llama.cpp load kwargs."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config

    @property
    def model_path(self) -> Path:
        return Path(self._config.model.path).expanduser().resolve()

    def validate(self) -> Path:
        path = self.model_path
        if not path.is_file():
            raise GGUFLoadError(f"GGUF model file not found: {path}")
        if path.suffix.lower() != ".gguf":
            raise GGUFLoadError(f"Expected a .gguf file, got: {path.name}")
        return path

    def llama_kwargs(self) -> dict:
        self.validate()
        model = self._config.model
        hardware = self._config.hardware
        return {
            "model_path": str(self.model_path),
            "n_ctx": model.n_ctx,
            "n_batch": model.n_batch,
            "n_gpu_layers": hardware.n_gpu_layers,
            "n_threads": hardware.n_threads or None,
            "verbose": False,
        }

    @staticmethod
    def from_model_config(model: ModelConfig, *, n_gpu_layers: int = 0, n_threads: int = 0) -> GGUFLoader:
        return GGUFLoader(
            RuntimeConfig(
                model=model,
                hardware=HardwareConfig(n_gpu_layers=n_gpu_layers, n_threads=n_threads),
            )
        )
