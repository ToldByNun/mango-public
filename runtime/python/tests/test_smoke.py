from __future__ import annotations

import os

import pytest

from devdeck_runtime.model_runner import ModelRunner

pytestmark = pytest.mark.smoke

MODEL_PATH = os.environ.get("DEVDECK_GGUF_MODEL_PATH", "")


@pytest.mark.skipif(not MODEL_PATH, reason="Set DEVDECK_GGUF_MODEL_PATH to a local .gguf file")
def test_load_and_complete() -> None:
    runner = ModelRunner()
    assert runner.config.model.path

    with runner:
        assert runner.is_loaded
        result = runner.complete("Say exactly: DevDeck runtime OK.", max_tokens=32)
        assert result.text.strip()
        assert result.completion_tokens > 0
        assert result.model_path.endswith(".gguf")


@pytest.mark.skipif(not MODEL_PATH, reason="Set DEVDECK_GGUF_MODEL_PATH to a local .gguf file")
def test_streaming_completion() -> None:
    with ModelRunner() as runner:
        chunks = list(runner.complete_stream("Count to three.", max_tokens=32))
        assert "".join(chunks).strip()
