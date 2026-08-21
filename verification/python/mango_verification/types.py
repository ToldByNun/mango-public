from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Diagnostic:
    message: str
    path: str | None = None
    line: int | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "severity": self.severity,
        }

    def compact_line(self) -> str:
        loc = self.path or ""
        if self.line:
            loc = f"{loc}:{self.line}" if loc else f"line {self.line}"
        prefix = f"{loc}: " if loc else ""
        return f"{prefix}{self.message}".strip()


@dataclass
class TestSummary:
    passed: int = 0
    failed: int = 0
    failed_names: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    collection_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "failed_names": self.failed_names,
            "errors": self.errors,
            "collection_errors": self.collection_errors,
        }


@dataclass
class StepResult:
    command: str
    skipped: bool
    exit_code: int = 0
    output: str = ""

    @property
    def ok(self) -> bool:
        return self.skipped or self.exit_code == 0


@dataclass
class VerificationResult:
    success: bool
    build_output: str
    test_output: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    test_summary: TestSummary | None = None
    build: StepResult | None = None
    test: StepResult | None = None
    lint: StepResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "build_output": self.build_output,
            "test_output": self.test_output,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "test_summary": None if self.test_summary is None else self.test_summary.to_dict(),
        }

    def compact_report(self, *, attempt: int | None = None, max_attempts: int | None = None) -> str:
        lines: list[str] = []
        if attempt is not None and max_attempts is not None:
            status = "passed" if self.success else "failed"
            lines.append(f"Verification {status} (attempt {attempt}/{max_attempts})")
        else:
            lines.append("Verification passed." if self.success else "Verification failed.")
        if self.build and not self.build.skipped:
            lines.append("Build: ok" if self.build.ok else f"Build: exit {self.build.exit_code}")
        collection = list((self.test_summary.collection_errors if self.test_summary else []) or [])
        if collection:
            files = ", ".join(collection[:3])
            lines.append(
                "COLLECTION ERROR: tests could not be imported. "
                f"Repair syntax/imports in {files} before changing assertions."
            )
            if self.test_summary:
                for err in self.test_summary.errors[:3]:
                    lines.append(f"  {err}")
            from mango_verification.parsers import parse_missing_import

            missing = parse_missing_import(
                "\n".join(
                    [self.test_output or "", *list((self.test_summary.errors if self.test_summary else []) or [])]
                )
            )
            if missing:
                name, module = missing
                loc = f"{module.replace('.', '/')}.py" if module else "the implementation module"
                lines.append(f"Define missing symbol {name} in {loc}; do not change the test.")
        parsed = bool(
            self.test_summary
            and not collection
            and (self.test_summary.passed or self.test_summary.failed or self.test_summary.failed_names)
        )
        if parsed and self.test_summary:
            lines.append(f"Tests: {self.test_summary.passed} passed, {self.test_summary.failed} failed")
            for name in self.test_summary.failed_names[:5]:
                lines.append(f"- {name}")
            for err in self.test_summary.errors[:4]:
                lines.append(f"  {err}")
        elif not collection and self.test and not self.test.skipped and not self.test.ok:
            lines.append(f"Tests: exit {self.test.exit_code}")
            for raw in self.test.output.splitlines()[-5:]:
                if raw.strip() and "PytestConfigWarning" not in raw:
                    lines.append(raw.strip()[:200])
        for diag in self.diagnostics[:8]:
            lines.append(f"- {diag.compact_line()}")
        text = "\n".join(lines).strip()
        if len(text) > 900:
            return text[:880].rstrip() + "\n...[truncated]"
        return text
