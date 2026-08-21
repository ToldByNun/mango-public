from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evidence:
    source: str
    snippet: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "snippet": self.snippet}


@dataclass
class EpistemicResult:
    exists: bool | None
    signature: str | None = None
    details: str | None = None
    version: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    conflicts: list[str] | None = None
    question: str = ""
    looked_up: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "signature": self.signature,
            "details": self.details,
            "version": self.version,
            "evidence": [item.to_dict() for item in self.evidence],
            "conflicts": self.conflicts,
            "question": self.question,
        }

    def to_compact_dict(self) -> dict[str, Any]:
        """Payload returned to the main agent — no sub-agent history."""
        evidence = [item.to_dict() for item in self.evidence[:3]]
        for item in evidence:
            snippet = item.get("snippet") or ""
            if len(snippet) > 160:
                item["snippet"] = snippet[:157] + "..."
        details = self.details or ""
        if len(details) > 2_200:
            details = details[:2_197] + "..."
        signature = self.signature or ""
        if len(signature) > 400:
            signature = signature[:397] + "..."
        return {
            "exists": self.exists,
            "signature": signature or None,
            "details": details or None,
            "version": self.version,
            "evidence": evidence,
            "conflicts": self.conflicts,
            "looked_up": list(self.looked_up) or None,
        }
