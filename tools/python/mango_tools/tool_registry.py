from __future__ import annotations

from typing import Any, Callable

from mango_tools.types import ToolDefinition, ToolSchema


class ToolRegistry:
    """Plugin-style registry for tool handlers."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        required: list[str] | None = None,
    ) -> None:
        if not name or not name.replace("_", "").isalnum():
            raise ValueError(f"Invalid tool name: {name!r}")
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

        schema = ToolSchema(
            name=name,
            description=description,
            parameters=parameters or {},
            required=required or [],
        )
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            handler=handler,
            schema=schema,
        )

    def tool(
        self,
        name: str,
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        required: list[str] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                name,
                func,
                description=description or (func.__doc__ or "").strip(),
                parameters=parameters,
                required=required,
            )
            return func

        return decorator

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[ToolSchema]:
        return [tool.schema for tool in self._tools.values()]

    def clear(self) -> None:
        self._tools.clear()
