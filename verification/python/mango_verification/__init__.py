"""Mango Verification — treat generated code as a hypothesis until the environment confirms it."""

from mango_verification.config import VerificationConfig, load_verification_config
from mango_verification.ledger import VerificationLedger
from mango_verification.map_failures import map_failed_tests, symbol_from_test_name
from mango_verification.types import Diagnostic, TestSummary, VerificationResult
from mango_verification.verifier import build_step, diagnostics_step, run_verification, test_step

__all__ = [
    "Diagnostic",
    "TestSummary",
    "VerificationConfig",
    "VerificationLedger",
    "VerificationResult",
    "build_step",
    "diagnostics_step",
    "load_verification_config",
    "map_failed_tests",
    "run_verification",
    "symbol_from_test_name",
    "test_step",
]
