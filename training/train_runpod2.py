#!/usr/bin/env python3
"""
RunPod pipeline for Qwen3.8-27B (NF4 QLoRA → FP16 merge → IQ2_XXS GGUF).

Designed for large GPUs (A100 40/80GB, H100) with plenty of system RAM for CPU merge.

Steps (default: all three):
  1. NF4 QLoRA SFT via Unsloth
  2. Merge LoRA → FP16 on CPU (needs ~55GB RAM for 27B)
  3. Export llama.cpp GGUF (default: iq2_xxs)

Examples:
  pip install -r requirements.txt
  python train_runpod.py --no_wandb
  python train_runpod.py --no_wandb --resume_from_checkpoint output/qwen3.8-27b-mango/checkpoint-500
  # Fresh LR from existing LoRA (do NOT use --resume_from_checkpoint):
  python train_runpod.py --no_wandb --train_only \
    --adapter output/qwen3.8-27b-mango/checkpoint-700 \
    --continue_output_dir output/qwen3.8-27b-mango-cont700 \
    --lr 1.5e-5 --max_steps 200
  python train_runpod.py --train_only --no_wandb
  python train_runpod.py --merge_only
  python train_runpod.py --export_gguf_only --gguf_quant iq2_xxs
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from pathlib import Path
from typing import Any

# RunPod/Linux: skip Windows-only patches from finetune_qwen_coder.py
if "--no_wandb" in sys.argv:
    os.environ["WANDB_DISABLED"] = "true"
    os.environ["WANDB_MODE"] = "disabled"

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


def _require_cuda() -> None:
    """Fail early with a clear message when torch cannot see the GPU."""
    import torch

    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        free, total = torch.cuda.mem_get_info()
        print(
            f"[runpod] CUDA OK: {name} | "
            f"{(total - free) / 1e9:.1f}/{total / 1e9:.1f} GB used | "
            f"torch={torch.__version__} cuda={torch.version.cuda}"
        )
        return
    print(
        "[runpod] CUDA NOT AVAILABLE — Unsloth needs a working torch+GPU.\n"
        "  Common on RunPod: PyTorch built for newer CUDA than the host driver.\n"
        "  Your log showed driver CUDA 12.8 (version 12080).\n"
        "  Fix:\n"
        "    bash setup_runpod.sh\n"
        "  Or manually:\n"
        "    pip uninstall -y torch torchvision torchaudio\n"
        "    pip install torch torchvision torchaudio "
        "--index-url https://download.pytorch.org/whl/cu128\n"
        "  Then: python -c \"import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))\"",
        file=sys.stderr,
    )
    raise SystemExit(1)


_require_cuda()

# Unsloth must be imported BEFORE trl/transformers/peft.
from unsloth import FastLanguageModel  # noqa: E402
from datasets import Dataset  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402

MODEL_NAME = "unsloth/Qwen3.8-27B"
MAX_SEQ_LENGTH = 2048
DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "mango_sft_10000.jsonl"
OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "qwen3.8-27b-mango"
LORA_DIR = "lora"
MERGED_DIR = "merged_fp16"
GGUF_DIR = "gguf_iq2_xxs"


def load_and_format(path: Path, tok) -> list[str]:
    texts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        texts.append(
            tok.apply_chat_template(
                row["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )
        )
    return texts


def _vram_note(label: str) -> None:
    import torch

    if not torch.cuda.is_available():
        return
    free, total = torch.cuda.mem_get_info()
    print(f"[runpod] {label}: {(total - free) / 1e9:.1f}/{(total) / 1e9:.1f} GB VRAM used")


def train_qlora(args: argparse.Namespace) -> tuple[Any, Any]:
    # --adapter: load LoRA weights only (fresh optimizer/LR). Do NOT combine with
    # --resume_from_checkpoint (that restores the dead cosine schedule too).
    if args.adapter and args.resume_from_checkpoint:
        raise SystemExit(
            "[runpod] use either --adapter (fresh LR) or --resume_from_checkpoint "
            "(full resume), not both"
        )

    if args.adapter:
        adapter = Path(args.adapter)
        if not adapter.is_dir():
            raise FileNotFoundError(f"Adapter not found: {adapter}")
        print(f"[runpod] loading adapter weights from {adapter} (fresh LR schedule)")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(adapter),
            max_seq_length=args.max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )
    else:
        print(f"[runpod] loading {args.model} (4-bit NF4) ...")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=args.model,
            max_seq_length=args.max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )
        _vram_note("after base load")

        model = FastLanguageModel.get_peft_model(
            model,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            bias="none",
            use_gradient_checkpointing=True,
            random_state=42,
        )
    _vram_note("after LoRA")

    print(f"[runpod] dataset {args.dataset}")
    texts = load_and_format(args.dataset, tokenizer)
    print(f"[runpod] {len(texts)} examples, first sample {len(texts[0])} chars")
    ds = Dataset.from_dict({"text": texts}).shuffle(seed=args.seed)
    print(f"[runpod] shuffled dataset (seed={args.seed})")

    # Avoid writing over the old run's checkpoints when continuing from an adapter.
    out_dir = args.output_dir
    if args.adapter and args.continue_output_dir:
        out_dir = Path(args.continue_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    training_args = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        bf16=True,
        optim="adamw_8bit",
        max_seq_length=args.max_seq_length,
        packing=True,
        dataset_text_field="text",
        logging_steps=10,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=8,
        report_to="none",
        seed=args.seed,
        dataloader_num_workers=2,
        dataloader_pin_memory=True,
        group_by_length=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        args=training_args,
    )

    print(
        f"[runpod] starting QLoRA training ... lr={args.lr} max_steps={args.max_steps} "
        f"out={out_dir}"
    )
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    # Final LoRA save always under the run's output dir.
    args.output_dir = out_dir

    lora_path = args.output_dir / LORA_DIR
    print(f"[runpod] saving LoRA adapter → {lora_path}")
    model.save_pretrained(str(lora_path))
    tokenizer.save_pretrained(str(lora_path))
    return model, tokenizer


def merge_fp16_cpu(args: argparse.Namespace) -> None:
    """Merge LoRA into FP16 weights on CPU (high system RAM, low VRAM pressure)."""
    import torch

    lora_path = args.output_dir / LORA_DIR
    merged_path = args.output_dir / MERGED_DIR
    if not lora_path.is_dir():
        raise FileNotFoundError(f"LoRA adapter not found: {lora_path}")

    print(f"[runpod] loading base + LoRA for CPU merge from {lora_path}")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(lora_path),
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=False,
        device_map="cpu",
    )
    FastLanguageModel.for_inference(model)

    merged_path.mkdir(parents=True, exist_ok=True)
    print(f"[runpod] merging → {merged_path} (FP16, CPU) — expect several minutes / ~55GB RAM")
    model.save_pretrained_merged(
        str(merged_path),
        tokenizer,
        save_method="merged_16bit",
    )
    tokenizer.save_pretrained(str(merged_path))
    print(f"[runpod] merged FP16 saved at {merged_path}")

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def export_gguf(args: argparse.Namespace) -> None:
    """Quantize merged FP16 to llama.cpp GGUF (default IQ2_XXS)."""
    merged_path = args.output_dir / MERGED_DIR
    gguf_path = args.output_dir / GGUF_DIR
    if not merged_path.is_dir():
        raise FileNotFoundError(f"Merged FP16 model not found: {merged_path}")

    print(f"[runpod] loading merged FP16 from {merged_path}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(merged_path),
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=False,
    )
    FastLanguageModel.for_inference(model)

    gguf_path.mkdir(parents=True, exist_ok=True)
    print(f"[runpod] exporting GGUF quant={args.gguf_quant} → {gguf_path}")
    # IQ* quants need an importance matrix; True = fetch Unsloth upstream imatrix.
    raw = str(args.imatrix_file).strip().lower()
    if raw in ("true", "1", "yes"):
        imatrix: bool | str = True
    elif raw in ("false", "0", "no", "none", ""):
        imatrix = False
    else:
        imatrix = args.imatrix_file
    print(f"[runpod] imatrix_file={imatrix!r}")
    model.save_pretrained_gguf(
        str(gguf_path),
        tokenizer,
        quantization_method=args.gguf_quant,
        imatrix_file=imatrix,
    )
    print(f"[runpod] GGUF export done: {gguf_path}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="RunPod Qwen3.8-27B QLoRA → FP16 → IQ2_XXS")
    ap.add_argument("--model", default=MODEL_NAME, help="Unsloth 4-bit base (NVFP4)")
    ap.add_argument("--dataset", type=Path, default=DATASET_PATH)
    ap.add_argument("--output_dir", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--max_seq_length", type=int, default=MAX_SEQ_LENGTH)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch_size", type=int, default=2)
    ap.add_argument("--grad_accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-6)
    ap.add_argument("--lora_r", type=int, default=32)
    ap.add_argument("--lora_alpha", type=int, default=64)
    ap.add_argument("--warmup_ratio", type=float, default=0.03)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--max_steps", type=int, default=-1)
    ap.add_argument("--save_steps", type=int, default=100)
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Shuffle + trainer seed. Change (e.g. 123) for a different data mix on continue runs.",
    )
    ap.add_argument("--resume_from_checkpoint", default=None)
    ap.add_argument(
        "--adapter",
        default=None,
        help="Load LoRA from this folder (e.g. checkpoint-700) with a FRESH optimizer/LR. "
        "Prefer this over --resume_from_checkpoint when changing LR.",
    )
    ap.add_argument(
        "--continue_output_dir",
        default=None,
        help="When using --adapter, write new checkpoints here (default: same --output_dir).",
    )
    ap.add_argument("--gguf_quant", default="iq2_xxs", help="llama.cpp quant, e.g. iq2_xs")
    ap.add_argument(
        "--imatrix_file",
        default="true",
        help="IQ* importance matrix: 'true' = Unsloth upstream (needs base-model metadata), "
        "or path to .dat/.gguf. For merged FP16 use e.g. downloaded "
        "unsloth/Qwen3.8-27B-GGUF imatrix_unsloth.dat",
    )
    ap.add_argument("--no_wandb", action="store_true")

    stage = ap.add_mutually_exclusive_group()
    stage.add_argument("--train_only", action="store_true")
    stage.add_argument("--merge_only", action="store_true")
    stage.add_argument("--export_gguf_only", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(f"[runpod] output_dir={args.output_dir}")

    if args.export_gguf_only:
        export_gguf(args)
        return

    if args.merge_only:
        merge_fp16_cpu(args)
        return

    model, tokenizer = train_qlora(args)
    del model, tokenizer
    gc.collect()

    if args.train_only:
        print("[runpod] train_only — skipping merge/export")
        return

    merge_fp16_cpu(args)
    export_gguf(args)
    print(f"[runpod] pipeline complete → {args.output_dir}")


if __name__ == "__main__":
    main()
