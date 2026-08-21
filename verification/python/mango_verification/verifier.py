from __future__ import annotations

from pathlib import Path

from mango_verification.config import VerificationConfig, load_verification_config
from mango_verification.parsers import parse_diagnostics, parse_test_output
from mango_verification.runners.command import clear_bytecode_caches, run_command
from mango_verification.types import Diagnostic, StepResult, VerificationResult


def build_step(project_path: str | Path, config: VerificationConfig | dict | str | None = None) -> StepResult:
    loaded = load_verification_config(project_path, config)
    return run_command(project_path, loaded.build)


def test_step(project_path: str | Path, config: VerificationConfig | dict | str | None = None) -> StepResult:
    loaded = load_verification_config(project_path, config)
    return run_command(project_path, loaded.test)


def diagnostics_step(project_path: str | Path, config: VerificationConfig | dict | str | None = None) -> StepResult:
    loaded = load_verification_config(project_path, config)
    return run_command(project_path, loaded.diagnostics)


def run_verification(
    project_path: str | Path,
    config: VerificationConfig | dict | str | None = None,
) -> VerificationResult:
    loaded = load_verification_config(project_path, config)
    clear_bytecode_caches(project_path)
    build = build_step(project_path, loaded)
    test = test_step(project_path, loaded)
    lint = diagnostics_step(project_path, loaded)

    diagnostics: list[Diagnostic] = []
    if not build.skipped and not build.ok:
        diagnostics.extend(parse_diagnostics(build.output))
    test_summary = None
    if not test.skipped:
        test_summary = parse_test_output(test.output)
        if not test.ok:
            diagnostics.extend(parse_diagnostics(test.output))
    if not lint.skipped and not lint.ok:
        diagnostics.extend(parse_diagnostics(lint.output, default_severity="warning"))

    success = build.ok and test.ok and lint.ok
    if test_summary and test_summary.failed > 0:
        success = False

    return VerificationResult(
        success=success,
        build_output=build.output,
        test_output=test.output,
        diagnostics=diagnostics,
        test_summary=test_summary,
        build=build,
        test=test,
        lint=lint,
    )
