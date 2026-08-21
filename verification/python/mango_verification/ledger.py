from __future__ import annotations

from dataclasses import dataclass, field

from mango_verification.types import VerificationResult


@dataclass
class TrackedIssue:
    test_name: str
    status: str = "still_failing"
    symbol: str | None = None
    impl_path: str | None = None
    message: str = ""
    visible_until: int | None = None


@dataclass
class VerificationLedger:
    """Cumulative verification status across fix-loop attempts."""

    issues: dict[str, TrackedIssue] = field(default_factory=dict)
    generation: int = 0

    def ingest(
        self,
        result: VerificationResult,
        mappings: list[dict] | None = None,
        *,
        attempt: int | None = None,
        max_attempts: int | None = None,
    ) -> str:
        self.generation += 1
        mapping_by_name = {str(item.get("test_name")): item for item in (mappings or [])}
        failing = list((result.test_summary.failed_names if result.test_summary else []) or [])
        if not failing and not result.success and result.test_summary and result.test_summary.failed:
            failing = [f"(unnamed fail {i})" for i in range(result.test_summary.failed)]

        for name in failing:
            issue = self.issues.setdefault(name, TrackedIssue(test_name=name))
            issue.status = "still_failing"
            issue.visible_until = None
            meta = mapping_by_name.get(name) or {}
            if meta.get("symbol"):
                issue.symbol = str(meta["symbol"])
            if meta.get("impl_path"):
                issue.impl_path = str(meta["impl_path"])
            if meta.get("message"):
                issue.message = str(meta["message"])

        failing_set = set(failing)
        for name, issue in self.issues.items():
            if name in failing_set:
                continue
            if issue.status == "still_failing":
                issue.status = "fixed"
                issue.visible_until = self.generation + 1
            meta = mapping_by_name.get(name) or {}
            if meta.get("symbol") and not issue.symbol:
                issue.symbol = str(meta["symbol"])
            if meta.get("impl_path") and not issue.impl_path:
                issue.impl_path = str(meta["impl_path"])

        return self.render(result, attempt=attempt, max_attempts=max_attempts)

    def still_failing_names(self) -> list[str]:
        return [issue.test_name for issue in self.issues.values() if issue.status == "still_failing"]

    def impl_paths(self, *, failing_only: bool = True) -> list[str]:
        paths: list[str] = []
        for issue in self.issues.values():
            if failing_only and issue.status != "still_failing":
                continue
            if issue.impl_path and issue.impl_path not in paths:
                paths.append(issue.impl_path)
        return paths

    def impl_symbols(self, *, failing_only: bool = True) -> list[str]:
        symbols: list[str] = []
        for issue in self.issues.values():
            if failing_only and issue.status != "still_failing":
                continue
            if issue.symbol and issue.symbol not in symbols:
                symbols.append(issue.symbol)
        return symbols

    def next_edit_hint(self) -> str:
        for issue in self.issues.values():
            if issue.status != "still_failing":
                continue
            path = issue.impl_path or "?"
            name = issue.symbol or "?"
            assertion = " ".join((issue.message or "").split())[:120]
            hint = f"Edit {path} symbol {name}"
            if assertion:
                hint += f": {assertion}"
            return hint
        return ""

    def render(
        self,
        result: VerificationResult,
        *,
        attempt: int | None = None,
        max_attempts: int | None = None,
    ) -> str:
        if attempt is not None and max_attempts is not None:
            status = "passed" if result.success else "failed"
            lines = [f"Verification {status} (attempt {attempt}/{max_attempts})"]
        else:
            lines = ["Verification passed." if result.success else "Verification failed."]
        if result.test_summary:
            lines.append(
                f"Tests: {result.test_summary.passed} passed, {result.test_summary.failed} failed"
            )
        fixed_bits = [
            _format_fixed(issue)
            for issue in self.issues.values()
            if issue.status == "fixed" and self._visible(issue)
        ]
        failing_bits = [
            _format_failing(issue)
            for issue in self.issues.values()
            if issue.status == "still_failing"
        ]
        if fixed_bits:
            lines.append("fixed: " + " | ".join(fixed_bits))
        if failing_bits:
            lines.append("still failing: " + " | ".join(failing_bits))
        if result.test_summary:
            # Include a bit more failing detail so the agent has enough signal
            # to pick a targeted fix, while still keeping the whole report compact.
            for err in result.test_summary.errors[:8]:
                if err:
                    lines.append(f"  {err}")
        excerpt = _test_output_excerpt(getattr(result, "test_output", "") or "")
        if excerpt:
            lines.append("test output excerpt:")
            lines.extend(f"  {line}" for line in excerpt)
        text = "\n".join(lines).strip()
        if len(text) > 1_500:
            return text[:1_470].rstrip() + "\n...[truncated]"
        return text

    def _visible(self, issue: TrackedIssue) -> bool:
        if issue.status == "still_failing":
            return True
        if issue.visible_until is None:
            return False
        return self.generation <= issue.visible_until


def _short_test(name: str) -> str:
    return name.split("::")[-1]


def _format_fixed(issue: TrackedIssue) -> str:
    loc = f" ({issue.impl_path})" if issue.impl_path else ""
    return f"{_short_test(issue.test_name)}{loc}"


def _format_failing(issue: TrackedIssue) -> str:
    target = ""
    if issue.impl_path and issue.symbol:
        target = f" -> {issue.impl_path}: {issue.symbol}()"
    elif issue.impl_path:
        target = f" -> {issue.impl_path}"
    elif issue.symbol:
        target = f" -> {issue.symbol}()"
    return f"{_short_test(issue.test_name)}{target}"


def _test_output_excerpt(output: str, *, max_lines: int = 8) -> list[str]:
    rows: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or "PytestConfigWarning" in line:
            continue
        rows.append(line[:220])
    if not rows:
        return []
    if len(rows) <= max_lines:
        return rows
    return rows[-max_lines:]
