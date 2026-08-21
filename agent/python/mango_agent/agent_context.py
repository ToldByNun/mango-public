"""Limits and workspace settings for the full main agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mango_agent.types import AgentLimits


@dataclass
class WorkspaceConfig:
    """Project roots shared by codeintel and verification."""

    root: Path
    codeintel_root: Path | None = None
    verification_root: Path | None = None

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.codeintel_root = Path(self.codeintel_root).resolve() if self.codeintel_root else self.root
        self.verification_root = (
            Path(self.verification_root).resolve() if self.verification_root else self.root
        )


@dataclass
class AgentContextConfig:
    workspace: WorkspaceConfig
    limits: AgentLimits = field(default_factory=AgentLimits)
    system_prompt: str | None = None


__all__ = ["AgentContextConfig", "AgentLimits", "WorkspaceConfig"]
