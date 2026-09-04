from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelConfig:
    path: str
    n_ctx: int = 4096
    n_batch: int = 512
    n_ubatch: int = 0  # 0 = auto (min(n_batch, 512))


@dataclass(frozen=True)
class HardwareConfig:
    n_gpu_layers: int = 0
    n_threads: int = 0


@dataclass(frozen=True)
class InferenceConfig:
    max_tokens: int = 256
    temperature: float = 0.1
    top_p: float = 0.95
    stop: list[str] = field(default_factory=list)
    # 1.0 disables the penalty, which makes low-temperature quantized models
    # repeat one sentence until the token budget is gone.
    repeat_penalty: float = 1.12
    repeat_last_n: int = 256


class ConfigValidationError(ValueError):
    """Invalid runtime config at the load edge."""


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigValidationError(f"{label} must be a mapping, got {type(value).__name__}")
    return value


def _as_int(value: Any, label: str, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(f"{label} must be an integer") from exc


def _as_float(value: Any, label: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(f"{label} must be a number") from exc


@dataclass(frozen=True)
class RuntimeConfig:
    model: ModelConfig
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeConfig:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigValidationError(f"config root must be a mapping, got {type(data).__name__}")
        model = _require_mapping(data.get("model", {}), "model")
        hardware = _require_mapping(data.get("hardware", {}), "hardware")
        inference = _require_mapping(data.get("inference", {}), "inference")
        stop_raw = inference.get("stop", [])
        if stop_raw is None:
            stop_raw = []
        if not isinstance(stop_raw, list):
            raise ConfigValidationError("inference.stop must be a list")
        return cls(
            model=ModelConfig(
                path=str(model.get("path", "")),
                n_ctx=_as_int(model.get("n_ctx", 4096), "model.n_ctx", 4096),
                n_batch=_as_int(model.get("n_batch", 512), "model.n_batch", 512),
                n_ubatch=_as_int(model.get("n_ubatch", 0), "model.n_ubatch", 0),
            ),
            hardware=HardwareConfig(
                n_gpu_layers=_as_int(hardware.get("n_gpu_layers", 0), "hardware.n_gpu_layers", 0),
                n_threads=_as_int(hardware.get("n_threads", 0), "hardware.n_threads", 0),
            ),
            inference=InferenceConfig(
                max_tokens=_as_int(inference.get("max_tokens", 256), "inference.max_tokens", 256),
                temperature=_as_float(inference.get("temperature", 0.1), "inference.temperature", 0.1),
                top_p=_as_float(inference.get("top_p", 0.95), "inference.top_p", 0.95),
                stop=[str(item) for item in stop_raw],
                repeat_penalty=_as_float(
                    inference.get("repeat_penalty", 1.12), "inference.repeat_penalty", 1.12
                ),
                repeat_last_n=_as_int(
                    inference.get("repeat_last_n", 256), "inference.repeat_last_n", 256
                ),
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
    # Observability (A0a). Optional so FakeCompletion and older callers stay valid.
    ttft_ms: float = 0.0
    prefill_s: float = 0.0
    decode_s: float = 0.0
    reset_cache: bool = False
