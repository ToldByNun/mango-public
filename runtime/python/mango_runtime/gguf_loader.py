from __future__ import annotations

import os
from pathlib import Path

from mango_runtime.types import HardwareConfig, ModelConfig, RuntimeConfig


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
        is_windows = os.name == "nt"
        # Large n_batch speeds prompt prefill; smaller n_ubatch keeps decode latency low.
        n_ubatch = model.n_ubatch if model.n_ubatch > 0 else min(model.n_batch, 512)
        return {
            "model_path": str(self.model_path),
            "n_ctx": model.n_ctx,
            "n_batch": model.n_batch,
            "n_ubatch": n_ubatch,
            "n_gpu_layers": hardware.n_gpu_layers,
            "n_threads": hardware.n_threads or None,
            # Window the repeat penalty looks back over; the default 64 is too
            # short to break a repeated sentence.
            "last_n_tokens_size": max(64, self._config.inference.repeat_last_n),
            "offload_kqv": True,
            "flash_attn": True,
            # Gemma 4 ISWA: full-size SWA cache at n_ctx=16k fills 16GB and
            # first decode never starts (VRAM 100%, compute idle).
            "swa_full": False,
            # Q4_0 KV-Cache: half the VRAM of Q8_0, minimal quality loss for coding
            "type_k": 2,  # GGML_TYPE_Q4_0
            "type_v": 2,
            # Windows NTFS mmap is slower than direct read for large files
            "use_mmap": not is_windows,
            # Disable mlock on Windows (not supported well)
            "use_mlock": False,
            "verbose": os.environ.get("MANGO_LLAMA_VERBOSE", "").strip() in {"1", "true", "yes"},
        }

    @staticmethod
    def from_model_config(model: ModelConfig, *, n_gpu_layers: int = 0, n_threads: int = 0) -> GGUFLoader:
        return GGUFLoader(
            RuntimeConfig(
                model=model,
                hardware=HardwareConfig(n_gpu_layers=n_gpu_layers, n_threads=n_threads),
            )
        )
