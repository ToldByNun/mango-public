"""Load the local GGUF and time the first generated token. Prints nvidia-smi."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "runtime" / "python"))


def vram() -> str:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        return out.strip()
    except Exception as exc:  # noqa: BLE001
        return f"nvidia-smi failed: {exc}"


def main() -> int:
    n_ctx = int(sys.argv[1]) if len(sys.argv) > 1 else 4096
    print(f"[probe] n_ctx={n_ctx} vram_before={vram()}", flush=True)

    from mango_runtime.config import load_config
    from mango_runtime.model_runner import ModelRunner
    from mango_runtime.types import HardwareConfig, ModelConfig, RuntimeConfig

    base = load_config(REPO / "runtime" / "config.yaml")
    config = RuntimeConfig(
        model=ModelConfig(path=base.model.path, n_ctx=n_ctx, n_batch=min(base.model.n_batch, 256)),
        hardware=HardwareConfig(n_gpu_layers=base.hardware.n_gpu_layers, n_threads=base.hardware.n_threads),
        inference=base.inference,
    )
    runner = ModelRunner(config)
    t0 = time.monotonic()
    runner.load()
    print(f"[probe] loaded in {time.monotonic() - t0:.1f}s vram={vram()}", flush=True)

    tokens: list[str] = []

    def on_token(delta: str) -> None:
        if not tokens:
            print(f"[probe] first token after {time.monotonic() - t0:.1f}s {delta!r} vram={vram()}", flush=True)
        tokens.append(delta)

    t1 = time.monotonic()
    result = runner.complete(
        "Reply with the single word: ok",
        max_tokens=16,
        temperature=0.0,
        on_token=on_token,
    )
    print(
        f"[probe] done in {time.monotonic() - t1:.1f}s "
        f"text={result.text!r} completion_tokens={result.completion_tokens} vram={vram()}",
        flush=True,
    )
    runner.unload()
    return 0 if result.text.strip() else 1


if __name__ == "__main__":
    raise SystemExit(main())
