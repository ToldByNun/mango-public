from __future__ import annotations

import sys

from mango_tools.implementations.measure import measure


def test_measure_reports_median_ms() -> None:
    cmd = f'"{sys.executable}" -c "pass"'
    result = measure(cmd, repeats=3, timeout=15)
    assert result["ok"] is True
    assert result["command"] == cmd
    assert len(result["samples_ms"]) == 3
    assert result["median_ms"] is not None
    assert result["median_ms"] >= 0
    assert sorted(result["samples_ms"])[1] == result["median_ms"] or abs(
        sorted(result["samples_ms"])[1] - result["median_ms"]
    ) < 1e-6


def test_measure_rejects_empty_command() -> None:
    import pytest

    with pytest.raises(ValueError, match="empty"):
        measure("  ")
