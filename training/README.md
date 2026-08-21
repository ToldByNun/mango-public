# Mango SFT — Qwen Fine-Tuning

Fine-tunes Qwen coding models with 4-bit QLoRA via [Unsloth](https://unsloth.ai).

## Scripts

| Script | Hardware | Model |
|--------|----------|--------|
| `finetune_qwen_coder.py` | 16GB local (5070 Ti) | Qwen2.5-Coder-14B |
| `train_local.py` | **16GB VRAM + 32GB RAM** | Qwen3.8-27B → FP16 → IQ2_XXS |
| `train_runpod.py` | A100/H100 RunPod | Qwen3.8-27B (roomy defaults) |

## Setup

```bash
cd training
pip install -r requirements.txt
```

## Local: Qwen3.8-27B on 5070 Ti 16GB + 32GB DDR5

Same pipeline as RunPod (`NF4 → FP16 merge → IQ2_XXS`), offloaded for your rig:

| Stage | How it fits |
|-------|-------------|
| **Train** | `unsloth/Qwen3.8-27B` + bnb 4-bit; `bs=1`, `seq=512`, attn LoRA, disk offload |
| **Merge** | 27B FP16 ≈ 54GB → **Windows pagefile ≥64GB** on a fast SSD |
| **GGUF** | CPU-first load, export `iq2_xs` |

**Before merge:** Settings → System → About → Advanced system settings → Performance → Advanced → Virtual memory → Custom **65536 MB** (or more) on SSD.

```powershell
cd training

# Prefer staged runs (new terminal between stages clears VRAM cleanly):
python train_local.py --no_wandb --train_only
python train_local.py --merge_only
python train_local.py --export_gguf_only --gguf_quant iq2_xs
```

Defaults: `lr=5e-6`, `lora_r=16`, `grad_accum=16`, `save_steps=50`.  
`--lora_mlp` enables MLP adapters (often OOMs on 16GB).

Output: `training/output/qwen3.8-27b-mango-local/`

## 14B (existing)

```bash
python finetune_qwen_coder.py --no_wandb
python finetune_qwen_coder.py --no_wandb --resume_from_checkpoint output/qwen-coder-14b-mango/checkpoint-1100
```

## RunPod (40GB+ VRAM)

**GPU not found / driver 12080:** Torch is newer than the host CUDA driver. Fix once per pod:

```bash
cd /workspace   # or wherever train_runpod.py lives
bash setup_runpod.sh
# or:
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Then:

```bash
python train_runpod.py --no_wandb
```

## Loss / early stop

Format-heavy SFT can drive loss to ~0.05–0.15 mid-epoch (memorization). Prefer an earlier checkpoint. Cap with `--max_steps 500–800` if needed.

## Output layout

```
training/output/qwen3.8-27b-mango-local/
├── checkpoint-*/   # LoRA mid-train
├── lora/           # final adapter
├── merged_fp16/    # full FP16 (large)
└── gguf_iq2_xs/    # inference GGUF
```
