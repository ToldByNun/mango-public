from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from mango_agent import Agent, StopReason, create_agent

pytestmark = pytest.mark.smoke

MODEL_PATH = os.environ.get(
    "MANGO_GGUF_MODEL_PATH",
    r"C:\Users\mikaj\.ollama\models\gemma4-coding-Q4_K_M.gguf",
)


@pytest.mark.skipif(not Path(MODEL_PATH).is_file(), reason="GGUF model not available")
def test_e2e_file_read_edit_scenario() -> None:
    os.environ["MANGO_GGUF_MODEL_PATH"] = MODEL_PATH

    with tempfile.TemporaryDirectory(prefix="mango-agent-e2e-") as tmp:
        sample = Path(tmp) / "message.txt"
        sample.write_text("Hello Mango\n", encoding="utf-8")

        task = (
            f'Read the file "{sample}", replace "Mango" with "Agent", '
            "read it again, then summarize the final file content."
        )

        agent = create_agent(max_iterations=10, max_tokens=512)
        try:
            result = agent.run(task)
        finally:
            agent.close()

        assert result.stop_reason == StopReason.COMPLETED
        assert "Agent" in sample.read_text(encoding="utf-8")
        assert any(step.tool_results for step in result.steps)
