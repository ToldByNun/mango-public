"""Pydantic models for JSONL sidecar RPC params (agent boundary)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class RpcValidationError(Exception):
    """Invalid RPC envelope or params; mapped to ServeError in serve.py."""


class HealthParams(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LoadModelParams(BaseModel):
    model_config = ConfigDict(extra="ignore")


class GetSettingsParams(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SetModelPathParams(BaseModel):
    path: str

    @field_validator("path")
    @classmethod
    def path_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("path is empty")
        return value


class UpdateSettingsParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    n_ctx: int | None = None
    n_batch: int | None = None
    n_gpu_layers: int | None = None
    n_threads: int | None = None
    reload_model: bool | None = None


class RunParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = ""
    goal: str
    workspace: str | None = None
    generate_title: bool = False
    thinking_level: str = "off"
    thought_max_tokens: int | None = None
    mode: str = ""

    @field_validator("goal")
    @classmethod
    def goal_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal is empty")
        return value

    @field_validator("thought_max_tokens", mode="before")
    @classmethod
    def coerce_thought_max_tokens(cls, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("thought_max_tokens must be an integer") from exc


class GenerateTitleParams(BaseModel):
    goal: str

    @field_validator("goal")
    @classmethod
    def goal_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal is empty")
        return value


class CancelParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str | None = None


class ContinueStallParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str | None = None


class UndoParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str | None = None


class ConfirmParams(BaseModel):
    request_id: str
    allowed: bool = False

    @field_validator("request_id")
    @classmethod
    def request_id_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request_id is required")
        return value


class ShutdownParams(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RpcRequest(BaseModel):
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: Any | None = None


RPC_METHOD_SCHEMAS: dict[str, type[BaseModel]] = {
    "health": HealthParams,
    "load_model": LoadModelParams,
    "get_settings": GetSettingsParams,
    "set_model_path": SetModelPathParams,
    "update_settings": UpdateSettingsParams,
    "run": RunParams,
    "generate_title": GenerateTitleParams,
    "cancel": CancelParams,
    "continue_stall": ContinueStallParams,
    "undo_last_mutation": UndoParams,
    "confirm": ConfirmParams,
    "shutdown": ShutdownParams,
}


def format_validation_error(method: str, exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return f"{method}: invalid params" if method else "invalid params"
    parts: list[str] = []
    for err in errors:
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = str(err.get("msg", "invalid"))
        parts.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(parts)
    prefix = f"{method}: " if method else ""
    return f"{prefix}invalid params: {detail}"


def validate_params(schema: type[BaseModel], params: dict[str, Any], *, method: str = "") -> BaseModel:
    try:
        return schema.model_validate(params)
    except ValidationError as exc:
        raise RpcValidationError(format_validation_error(method, exc)) from None


def parse_rpc_message(raw: dict[str, Any]) -> tuple[str, BaseModel | dict[str, Any]]:
    """Parse a JSONL RPC message and validate params for known methods."""
    method = str(raw.get("method") or "").strip()
    params_raw = raw.get("params") if isinstance(raw.get("params"), dict) else {}
    schema = RPC_METHOD_SCHEMAS.get(method)
    if schema is None:
        return method, params_raw
    return method, validate_params(schema, params_raw, method=method)
