"""Pydantic request bodies for mango-studio-host HTTP API (zero-trust edge)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class StudioCallBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    requires_confirm: bool = False
    confirm_summary: str = ""
    timeout_s: float | None = None

    @field_validator("tool")
    @classmethod
    def tool_non_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("tool is required")
        return str(value)


class StudioResultBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str

    @field_validator("request_id")
    @classmethod
    def request_id_non_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("request_id is required")
        return str(value)


class SettingsUpdateBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirm_prop_threshold: int | None = None
    thinking_level: str | None = None
    model_path: str | None = None


class RunBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = "studio"
    goal: str = ""
    mode: str = "roblox"
    thinking_level: str | None = None
    selection: Any = None
    workspace: str = ""


class CancelBody(BaseModel):
    model_config = ConfigDict(extra="ignore")


class UndoBody(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LoadModelBody(BaseModel):
    model_config = ConfigDict(extra="ignore")


def validation_error_body(exc: ValidationError) -> dict[str, Any]:
    return {
        "error": "invalid_payload",
        "detail": exc.errors(),
    }
