"""Try → measure → decide: executor-side KEEP / REVERT verdicts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PERF_REGRESSION_RATIO = 0.03
MAX_REVERTS = 3
DEFAULT_HYPOTHESIS = "this edit"

_PERF_GOAL = re.compile(
    r"(?i)\b(faster|schnell(?:er)?|optimize|optimis(?:e|ation)?|performance|"
    r"benchmark|latency|speedup)\b|\bms\b"
)
_CLAIM_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


Decision = Literal["keep", "revert"]


@dataclass(frozen=True)
class ExperimentVerdict:
    decision: Decision
    reason: str
    hypothesis: str
    before: float | None = None
    after: float | None = None
    unit: str = "ms"
    delta_pct: float | None = None
    unsupported: bool = False


def goal_wants_perf(text: str) -> bool:
    return bool(_PERF_GOAL.search(text or ""))


def claimed_speedup_pct(text: str) -> float | None:
    match = _CLAIM_PCT.search(text or "")
    if not match:
        return None
    return float(match.group(1))


def hypothesis_from_thought(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return DEFAULT_HYPOTHESIS
    sentence = _SENTENCE_SPLIT.split(cleaned, maxsplit=1)[0].strip() or cleaned
    if len(sentence) > 180:
        return sentence[:177].rstrip() + "…"
    return sentence


def speed_delta_pct(before_ms: float, after_ms: float) -> float:
    if before_ms <= 0:
        return 0.0
    return round((before_ms - after_ms) / before_ms * 100, 1)


def decide_experiment(
    *,
    syntax_ok: bool,
    tests_ok: bool | None,
    before_ms: float | None = None,
    after_ms: float | None = None,
    claimed_speedup_pct: float | None = None,
    hypothesis: str = DEFAULT_HYPOTHESIS,
    command_changed: bool = False,
) -> ExperimentVerdict:
    hyp = (hypothesis or "").strip() or DEFAULT_HYPOTHESIS
    if not syntax_ok:
        return ExperimentVerdict(decision="revert", reason="syntax", hypothesis=hyp)
    if tests_ok is False:
        return ExperimentVerdict(decision="revert", reason="tests_failed", hypothesis=hyp)
    if command_changed:
        return ExperimentVerdict(
            decision="keep",
            reason="command_changed",
            hypothesis=hyp,
            before=before_ms,
            after=after_ms,
        )
    if before_ms is not None and after_ms is not None and before_ms > 0:
        delta = speed_delta_pct(before_ms, after_ms)
        if after_ms > before_ms * (1 + PERF_REGRESSION_RATIO):
            return ExperimentVerdict(
                decision="revert",
                reason="regression",
                hypothesis=hyp,
                before=before_ms,
                after=after_ms,
                delta_pct=delta,
            )
        missed_claim = (
            claimed_speedup_pct is not None and delta < float(claimed_speedup_pct)
        )
        return ExperimentVerdict(
            decision="keep",
            reason="unsupported" if missed_claim else "keep",
            hypothesis=hyp,
            before=before_ms,
            after=after_ms,
            delta_pct=delta,
            unsupported=missed_claim,
        )
    return ExperimentVerdict(
        decision="keep",
        reason="keep",
        hypothesis=hyp,
        before=before_ms,
        after=after_ms,
    )


def restore_snapshots(snapshots: dict[str, str]) -> list[str]:
    """Write non-empty snapshot bytes back. Empty snapshots (new files) are left as-is."""
    restored: list[str] = []
    for raw_path, previous in snapshots.items():
        if not previous.strip():
            continue
        path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(previous, encoding="utf-8")
        restored.append(str(path))
    return restored
