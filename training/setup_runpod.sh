#!/usr/bin/env bash
# RunPod GPU setup for train_runpod.py (Linux pod).
# Fixes: driver 12080 / torch CUDA mismatch / Unsloth "no accelerator"
#         + transformers vs kernels>=0.15 import crash
set -eu

echo "[mango] checking GPU ..."
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi missing — use a CUDA GPU template"
  exit 1
fi
nvidia-smi
nvidia-smi --query-gpu=driver_version,name --format=csv,noheader || true

echo "[mango] installing PyTorch cu128 (matches driver CUDA 12.8 / 12080) ..."
pip uninstall -y torch torchvision torchaudio 2>/dev/null || true
pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

echo "[mango] installing Unsloth stack ..."
# kernels>=0.15 breaks older transformers hub_kernels (needs version= on LayerRepository).
# Pin <0.15 until transformers on the pod is new enough.
pip install -U "unsloth[colab-new]" trl peft accelerate bitsandbytes "datasets>=4.3.0,<4.4.0" transformers
pip install "kernels>=0.12,<0.15"

echo "[mango] verifying CUDA + transformers import ..."
python - <<'PY'
import torch
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
print("cuda_runtime", torch.version.cuda)
if not torch.cuda.is_available():
    raise SystemExit(
        "CUDA still unavailable. Try a matching RunPod CUDA template, "
        "or: pip install torch --index-url https://download.pytorch.org/whl/cu124"
    )
print("device", torch.cuda.get_device_name(0))
print("vram_gb", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1))
from unsloth import FastLanguageModel  # noqa: F401
print("unsloth OK")
print("OK")
PY

echo "[mango] done. Run: python train_runpod.py --no_wandb"
