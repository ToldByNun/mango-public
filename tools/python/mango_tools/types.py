from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypedDict


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    raw: str
    start: int
    end: int


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str] = field(default_factory=list)


@dataclass
class ToolDefinition:
    name: str
    description: str
    handler: Callable[..., Any]
    schema: ToolSchema

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        missing = [key for key in self.schema.required if key not in arguments]
        if missing:
            raise ValueError(f"Missing required arguments for '{self.name}': {', '.join(missing)}")
        return arguments


class ToolResultEnvelope(TypedDict):
    success: bool
    tool_name: str
    output: Any
    error: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    success: bool
    tool_name: str
    output: Any = None
    error: str | None = None
    call: ToolCall | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }

    def to_envelope(self) -> ToolResultEnvelope:
        """Stable serialized contract at the tools process edge."""
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "output": self.output,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


def as_tool_result_envelope(payload: dict[str, Any]) -> ToolResultEnvelope:
    """Validate a dict against the tool result envelope (edge contract)."""
    if not isinstance(payload, dict):
        raise TypeError("tool result envelope must be a dict")
    if "success" not in payload or "tool_name" not in payload:
        raise ValueError("tool result envelope requires success and tool_name")
    return {
        "success": bool(payload["success"]),
        "tool_name": str(payload["tool_name"]),
        "output": payload.get("output"),
        "error": None if payload.get("error") is None else str(payload["error"]),
        "metadata": dict(payload["metadata"]) if isinstance(payload.get("metadata"), dict) else {},
    }
