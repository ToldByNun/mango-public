from __future__ import annotations

import time
from types import SimpleNamespace

from mango_runtime.model_runner import close_llama_with_timeout, neutralize_llama_destructor


def test_neutralize_skips_real_close() -> None:
    closed = {"n": 0}

    def real_close() -> None:
        closed["n"] += 1

    llama = SimpleNamespace(close=real_close, _stack=object())
    neutralize_llama_destructor(llama)
    llama.close()
    assert closed["n"] == 0


def test_neutralize_none() -> None:
    neutralize_llama_destructor(None)


def test_close_llama_runs_class_close() -> None:
    closed = {"n": 0}

    class FakeLlama:
        def close(self) -> None:
            closed["n"] += 1

    assert close_llama_with_timeout(FakeLlama(), timeout_s=1.0) is True
    assert closed["n"] == 1


def test_close_llama_times_out_without_blocking() -> None:
    class HangLlama:
        def close(self) -> None:
            time.sleep(8)

    started = time.monotonic()
    assert close_llama_with_timeout(HangLlama(), timeout_s=0.4) is False
    assert time.monotonic() - started < 2.0
