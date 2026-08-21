from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioMeta:
    scenario_id: str
    lang: str
    workflow: str
    difficulty: str
    bug_class: str
    turn: str = "single"  # single | A | B
    pair_id: str | None = None
    verification_tier: str = "sandbox"
    cwe: str | None = None
    pitfall: str | None = None


@dataclass
class Scenario:
    meta: ScenarioMeta
    system: str
    user: str
    assistant: str
    sandbox_files: dict[str, str] = field(default_factory=dict)
    audit_files: dict[str, str] = field(default_factory=dict)
    test_cmd: str | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.user},
                {"role": "assistant", "content": self.assistant},
            ]
        }

    def to_index_line(self) -> dict[str, Any]:
        m = self.meta
        return {
            "scenario_id": m.scenario_id,
            "lang": m.lang,
            "workflow": m.workflow,
            "difficulty": m.difficulty,
            "bug_class": m.bug_class,
            "turn": m.turn,
            "pair_id": m.pair_id,
            "verification_tier": m.verification_tier,
            "cwe": m.cwe,
            "pitfall": m.pitfall,
        }
