from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
GGUF = Path(os.environ.get("MANGO_GGUF_MODEL_PATH") or "")
if not GGUF.is_file():
    from mango_runtime.config import load_config

    try:
        GGUF = Path(load_config(REPO / "runtime" / "config.yaml").model.path)
    except Exception:
        GGUF = Path()

pytestmark = pytest.mark.smoke


@pytest.mark.skipif(not GGUF.is_file(), reason="local GGUF not configured")
def test_clamp_prompt_writes_files_and_pytest_passes() -> None:
    import runpy

    script = REPO / "agent" / "python" / "scripts" / "run_clamp_prompt.py"
    ns = runpy.run_path(str(script), run_name="not_main")
    assert ns["main"]() == 0
