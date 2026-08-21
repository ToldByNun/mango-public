from __future__ import annotations

from pathlib import Path

from mango_verification import load_verification_config, run_verification
from mango_verification.parsers import parse_diagnostics, parse_test_output


SAMPLE_PYTEST_FAIL = """
F                                                                        [100%]
================================== FAILURES ===================================
___________________________________ test_Y ____________________________________
test_y.py:4: in test_Y
    assert Y(1) == 2
E   assert 0 == 2
E    +  where 0 = Y(1)
=========================== short test summary info ===========================
FAILED test_y.py::test_Y - assert 0 == 2
============================== 1 failed in 0.04s ==============================
"""

SAMPLE_PYTEST_PASS = """
.                                                                        [100%]
============================== 1 passed in 0.02s ==============================
"""

SAMPLE_GCC = """
src/main.c:12:5: error: implicit declaration of function 'foo'
src/main.c:18:1: warning: unused variable 'tmp'
"""


def test_parse_pytest_failure_extracts_counts_and_names() -> None:
    summary = parse_test_output(SAMPLE_PYTEST_FAIL)
    assert summary.failed == 1
    assert summary.passed == 0
    assert summary.failed_names == ["test_y.py::test_Y"]
    assert any("assert 0 == 2" in item for item in summary.errors)


def test_parse_pytest_pass() -> None:
    summary = parse_test_output(SAMPLE_PYTEST_PASS)
    assert summary.passed == 1
    assert summary.failed == 0
    assert summary.failed_names == []


SAMPLE_PYTEST_COLLECTION = """
==================================== ERRORS ====================================
_________________ ERROR collecting test_uniqueutil.py _________________
ImportError while importing test module '/tmp/test_uniqueutil.py'.
test_uniqueutil.py:1: in <module>
    from uniqueutil import unique
uniqueutil.py:3: in <module>
    oops
E   SyntaxError: invalid syntax
=========================== short test summary info ===========================
ERROR test_uniqueutil.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.12s
"""


def test_parse_pytest_collection_error() -> None:
    summary = parse_test_output(SAMPLE_PYTEST_COLLECTION)
    assert summary.collection_errors == ["test_uniqueutil.py"]
    assert any("SyntaxError" in item for item in summary.errors)
    from mango_verification.types import StepResult, VerificationResult

    result = VerificationResult(
        success=False,
        build_output="",
        test_output=SAMPLE_PYTEST_COLLECTION,
        test_summary=summary,
        test=StepResult(command="pytest", skipped=False, exit_code=2, output=SAMPLE_PYTEST_COLLECTION),
    )
    report = result.compact_report(attempt=1, max_attempts=5)
    assert "COLLECTION ERROR" in report
    assert "test_uniqueutil.py" in report
    assert "SyntaxError" in report
    assert "PytestConfigWarning" not in report


SAMPLE_PYTEST_MISSING_IMPORT = """
==================================== ERRORS ====================================
_________________ ERROR collecting test_names.py _________________
ImportError while importing test module '/tmp/test_names.py'.
E   ImportError: cannot import name 'normalize' from 'names' (/tmp/names.py)
ERROR test_names.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
"""


def test_parse_missing_import_and_compact_report() -> None:
    from mango_verification.parsers import parse_missing_import
    from mango_verification.types import StepResult, VerificationResult

    assert parse_missing_import(SAMPLE_PYTEST_MISSING_IMPORT) == ("normalize", "names")
    summary = parse_test_output(SAMPLE_PYTEST_MISSING_IMPORT)
    result = VerificationResult(
        success=False,
        build_output="",
        test_output=SAMPLE_PYTEST_MISSING_IMPORT,
        test_summary=summary,
        test=StepResult(command="pytest", skipped=False, exit_code=2, output=SAMPLE_PYTEST_MISSING_IMPORT),
    )
    report = result.compact_report()
    assert "Define missing symbol normalize in names.py" in report
    assert "do not change the test" in report



def test_parse_compiler_diagnostics_include_file_and_line() -> None:
    diags = parse_diagnostics(SAMPLE_GCC)
    paths = {(item.path, item.line, item.severity) for item in diags}
    assert ("src/main.c", 12, "error") in paths
    assert any("implicit declaration" in item.message for item in diags)


def test_load_config_from_json(tmp_path: Path) -> None:
    path = tmp_path / "mango.verify.json"
    path.write_text(
        '{"test": {"command": "python -m pytest -q", "timeout": 30}, "build": "echo build"}',
        encoding="utf-8",
    )
    loaded = load_verification_config(tmp_path)
    assert loaded.test.command == "python -m pytest -q"
    assert loaded.test.timeout == 30
    assert loaded.build.command == "echo build"
    assert loaded.has_any_command()


def test_load_config_from_minimal_yaml(tmp_path: Path) -> None:
    (tmp_path / "mango.verify.yaml").write_text(
        "test:\n  command: cargo test\n  timeout: 45\n",
        encoding="utf-8",
    )
    loaded = load_verification_config(tmp_path)
    assert loaded.test.command == "cargo test"
    assert loaded.test.timeout == 45


def test_run_verification_on_failing_then_passing_pytest(tmp_path: Path) -> None:
    import sys

    (tmp_path / "y.py").write_text("def Y(x):\n    return x - 1\n", encoding="utf-8")
    (tmp_path / "test_y.py").write_text(
        "from y import Y\n\ndef test_Y():\n    assert Y(1) == 2\n",
        encoding="utf-8",
    )
    (tmp_path / "mango.verify.json").write_text(
        '{"test": {"command": "%s -m pytest -q --tb=short --rootdir=. -p no:cacheprovider", "timeout": 60}}'
        % sys.executable.replace("\\", "/"),
        encoding="utf-8",
    )

    failed = run_verification(tmp_path)
    assert failed.success is False
    assert failed.test_summary is not None
    assert failed.test_summary.failed >= 1
    report = failed.compact_report(attempt=1, max_attempts=5)
    assert "failed" in report.lower()
    assert "test_Y" in report or "test_y.py" in report
    assert "FULL RAW" not in report
    assert len(report) < 900

    (tmp_path / "y.py").write_text("def Y(x):\n    return x + 1\n", encoding="utf-8")
    passed = run_verification(tmp_path)
    assert passed.success is True
    assert passed.test_summary is not None
    assert passed.test_summary.passed >= 1
    assert passed.test_summary.failed == 0


def test_symbol_from_test_name() -> None:
    from mango_verification.map_failures import symbol_from_test_name

    assert symbol_from_test_name("test_feature.py::test_discount") == "discount"
    assert symbol_from_test_name("test_money") == "money"


def test_map_failed_tests_uses_codeintel_paths() -> None:
    from types import SimpleNamespace

    from mango_verification.map_failures import map_failed_tests

    intel = SimpleNamespace(
        get_symbol_definition=lambda name: (
            [SimpleNamespace(path="app/format.py", line=1)] if name == "money" else [SimpleNamespace(path="app/pricing.py", line=1)]
        )
    )
    mapped = map_failed_tests(
        ["test_feature.py::test_discount", "test_feature.py::test_money"],
        codeintel=intel,
    )
    by_sym = {item["symbol"]: item["impl_path"] for item in mapped}
    assert by_sym["discount"] == "app/pricing.py"
    assert by_sym["money"] == "app/format.py"


def test_ledger_keeps_fixed_status_across_two_cycles() -> None:
    from mango_verification.ledger import VerificationLedger
    from mango_verification.types import TestSummary, VerificationResult

    def _vr(failed_names: list[str], passed: int, failed: int) -> VerificationResult:
        return VerificationResult(
            success=failed == 0,
            build_output="",
            test_output="",
            test_summary=TestSummary(passed=passed, failed=failed, failed_names=failed_names),
        )

    mappings = [
        {"test_name": "test_feature.py::test_discount", "symbol": "discount", "impl_path": "app/pricing.py"},
        {"test_name": "test_feature.py::test_money", "symbol": "money", "impl_path": "app/format.py"},
    ]
    ledger = VerificationLedger()
    report1 = ledger.ingest(_vr(["test_feature.py::test_discount", "test_feature.py::test_money"], 0, 2), mappings)
    assert "still failing" in report1
    assert "test_discount" in report1
    assert "test_money" in report1
    assert "app/pricing.py" in report1
    assert "app/format.py" in report1
    assert "fixed:" not in report1

    report2 = ledger.ingest(_vr(["test_feature.py::test_money"], 1, 1), mappings)
    assert "fixed: test_discount (app/pricing.py)" in report2
    assert "still failing: test_money -> app/format.py: money()" in report2
    assert "test_discount" in report2
    assert report2 != report1

    report3 = ledger.ingest(_vr(["test_feature.py::test_money"], 1, 1), mappings)
    assert "fixed: test_discount (app/pricing.py)" in report3
    assert "still failing: test_money" in report3

