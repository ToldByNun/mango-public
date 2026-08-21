from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SymbolHit:
    name: str
    qualname: str
    kind: str
    path: str
    line: int
    col: int
    end_line: int
    signature: str = ""
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualname": self.qualname,
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "signature": self.signature,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class RefHit:
    name: str
    path: str
    line: int
    col: int
    kind: str
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "kind": self.kind,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class FileHit:
    path: str
    score: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "score": self.score, "reasons": self.reasons}


@dataclass(frozen=True)
class GitSnapshot:
    branch: str = ""
    changed_files: list[str] = field(default_factory=list)
    recent_commits: list[str] = field(default_factory=list)
    available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "changed_files": self.changed_files,
            "recent_commits": self.recent_commits,
            "available": self.available,
        }
