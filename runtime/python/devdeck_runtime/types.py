from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelConfig:
    path: str
    n_ctx: int = 4096
    n_batch: int = 512


@dataclass(frozen=True)
class HardwareConfig:
    n_gpu_layers: int = 0
    n_threads: int = 0


@dataclass(frozen=True)
class InferenceConfig:
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.9
    stop: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuntimeConfig:
    model: ModelConfig
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeConfig:
        model = data.get("model", {})
        hardware = data.get("hardware", {})
        inference = data.get("inference", {})
        return cls(
            model=ModelConfig(
                path=str(model.get("path", "")),
                n_ctx=int(model.get("n_ctx", 4096)),
                n_batch=int(model.get("n_batch", 512)),
            ),
            hardware=HardwareConfig(
                n_gpu_layers=int(hardware.get("n_gpu_layers", 0)),
                n_threads=int(hardware.get("n_threads", 0)),
            ),
            inference=InferenceConfig(
                max_tokens=int(inference.get("max_tokens", 256)),
                temperature=float(inference.get("temperature", 0.7)),
                top_p=float(inference.get("top_p", 0.9)),
                stop=list(inference.get("stop", [])),
            ),
        )


@dataclass(frozen=True)
class CompletionResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    stopped_eos: bool
    model_path: str
