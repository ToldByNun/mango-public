#!/usr/bin/env python3
"""
Local Qwen3.8-27B pipeline for RTX 5070 Ti 16GB + 32GB DDR5 (Windows).

Same stages as RunPod:
  1. NF4 QLoRA SFT
  2. Merge → FP16 (CPU + pagefile; 32GB alone is not enough for a full 27B FP16)
  3. llama.cpp GGUF IQ2_XS

VRAM budget (train):
  - 27B NF4 weights ~14–15GB
  - room left ~1–2GB → bs=1, short seq, attn-only LoRA, Unsloth GC offload

RAM budget (merge/export):
  - Full 27B FP16 ≈ 54GB — needs Windows pagefile ≥64GB (Settings → System → About →
    Advanced system settings → Performance → Advanced → Virtual memory).
  - Script clears CUDA first so all 32GB + pagefile go to the merge.

Examples:
  pip install -r requirements.txt
  python train_local.py --no_wandb
  python train_local.py --no_wandb --train_only
  python train_local.py --merge_only
  python train_local.py --export_gguf_only --gguf_quant iq2_xs
  python train_local.py --no_wandb --resume_from_checkpoint output/qwen3.8-27b-mango-local/checkpoint-200
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import site
import sys
from pathlib import Path
from typing import Any

# ---- Windows / Unsloth env (before heavy imports) ----


def _configure_windows_triton_cc() -> None:
    if os.name != "nt" or os.environ.get("CC"):
        return
    for root in (site.getusersitepackages(), *site.getsitepackages()):
        tcc = Path(root) / "triton" / "runtime" / "tcc" / "tcc.exe"
        if tcc.is_file():
            os.environ["CC"] = str(tcc)
            print(f"[local] Triton CC={tcc}")
            return


def _patch_datasets_pickle_py314() -> None:
    if sys.version_info < (3, 14):
        return
    try:
        import datasets.utils._dill as ds_dill
    except ImportError:
        return

    def _batch_setitems(self, items, *args, **kwargs):  # noqa: ANN001
        if getattr(self, "_legacy_no_dict_keys_sorting", False):
            return super(ds_dill.Pickler, self)._batch_setitems(items, *args, **kwargs)
        from dill import Pickler as DillPickler

        return DillPickler._batch_setitems(self, items, *args, **kwargs)

    ds_dill.Pickler._batch_setitems = _batch_setitems


_configure_windows_triton_cc()
_patch_datasets_pickle_py314()

if "--no_wandb" in sys.argv:
    os.environ["WANDB_DISABLED"] = "true"
    os.environ["WANDB_MODE"] = "disabled"

# Unsloth double-buffer = CPU↔GPU thrash on Windows; keep off unless offload_gc is on.
if "--offload_gc" not in sys.argv:
    os.environ.setdefault("UNSLOTH_DISABLE_DOUBLE_BUFFER", "1")

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
# Prefer GPU for compute; leave headroom for fragmentation.
os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")

from datasets import Dataset
from trl import SFTConfig, SFTTrainer
from unsloth import FastLanguageModel

MODEL_NAME = "unsloth/Qwen3.8-27B"  # BF16 safetensors → QLoRA (NOT *-NVFP4; that is inference-only)
# 4-bit 27B wants ~16–19GB; on 16GB keep seq short and allow disk offload.
MAX_SEQ_LENGTH = 512
DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "mango_sft_10000.jsonl"
OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "qwen3.8-27b-mango-local"
LORA_DIR = "lora"
MERGED_DIR = "merged_fp16"
GGUF_DIR = "gguf_iq2_xs"
OFFLOAD_DIR = "offload"


def _offload_folder(output_dir: Path) -> Path:
    path = output_dir / OFFLOAD_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_kwargs_16gb(output_dir: Path, *, load_in_4bit: bool) -> dict[str, Any]:
    """Keep GPU under ~13GB so activations/optimizer fit; spill rest to RAM/disk."""
    offload = _offload_folder(output_dir)
    kwargs: dict[str, Any] = {
        "offload_folder": str(offload),
        # Leave ~3GB VRAM free for AdamW-8bit + activations on a 16GB card.
        "max_memory": {0: "13GiB", "cpu": "28GiB"},
    }
    if load_in_4bit:
        kwargs["load_in_4bit"] = True
    return kwargs


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
        print(f"[local] {label}: no CUDA")
        return
    free, total = torch.cuda.mem_get_info()
    print(
        f"[local] {label}: {(total - free) / 1e9:.1f}/{(total) / 1e9:.1f} GB VRAM "
        f"({free / 1e9:.1f} free)"
    )


def _ram_note(label: str) -> None:
    try:
        import psutil
    except ImportError:
        return
    vm = psutil.virtual_memory()
    print(
        f"[local] {label}: RAM used {vm.used / 1e9:.1f}/{vm.total / 1e9:.1f} GB "
        f"({vm.available / 1e9:.1f} available)"
    )


def _clear_cuda() -> None:
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
        torch.cuda.synchronize()


def train_qlora(args: argparse.Namespace) -> tuple[Any, Any]:
    if "NVFP4" in args.model.upper() or "nvfp4" in args.model:
        print(
            "[local] WARNING: *-NVFP4 is for inference, not QLoRA training. "
            "Use unsloth/Qwen3.8-27B (default). Continuing anyway..."
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[local] loading {args.model} (bnb 4-bit / NF4) for 16GB card ...")
    print(f"[local] offload_folder={args.output_dir / OFFLOAD_DIR}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_length,
        dtype=None,
        **_load_kwargs_16gb(args.output_dir, load_in_4bit=True),
    )
    _vram_note("after base load")

    # "unsloth" GC → activations to RAM (needed for 27B@16GB; slower on Windows PCIe).
    gc_mode: Any = "unsloth"
    print(f"[local] gradient_checkpointing={gc_mode!r} (CPU offload for 16GB headroom)")

    # Attn-only LoRA: MLP adapters eat too much VRAM on 16GB with 27B.
    targets = ["q_proj", "k_proj", "v_proj", "o_proj"]
    if args.lora_mlp:
        targets.extend(["gate_proj", "up_proj", "down_proj"])
        print("[local] LoRA targets include MLP (higher VRAM)")

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        target_modules=targets,
        bias="none",
        use_gradient_checkpointing=gc_mode,
        random_state=42,
    )
    _vram_note("after LoRA")

    print(f"[local] dataset {args.dataset}")
    texts = load_and_format(args.dataset, tokenizer)
    print(f"[local] {len(texts)} examples, sample chars={len(texts[0])}")
    ds = Dataset.from_dict({"text": texts}).shuffle(seed=args.seed)
    print(f"[local] shuffled dataset (seed={args.seed})")

    training_args = SFTConfig(
        output_dir=str(args.output_dir),
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
        logging_steps=5,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=4,
        report_to="none",
        seed=args.seed,
        # Windows: workers>0 often fights VRAM + forks badly.
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        group_by_length=True,
        # Don't keep eval tensors around.
        gradient_checkpointing=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        args=training_args,
    )

    print(
        f"[local] train start  bs={args.batch_size}×{args.grad_accum} "
        f"seq={args.max_seq_length} lr={args.lr} r={args.lora_r}"
    )
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    lora_path = args.output_dir / LORA_DIR
    print(f"[local] saving LoRA → {lora_path}")
    model.save_pretrained(str(lora_path))
    tokenizer.save_pretrained(str(lora_path))
    return model, tokenizer


def merge_fp16_cpu(args: argparse.Namespace) -> None:
    """Merge LoRA → FP16 on CPU. Needs ~54GB virtual memory for 27B."""
    import torch

    lora_path = args.output_dir / LORA_DIR
    merged_path = args.output_dir / MERGED_DIR
    if not lora_path.is_dir():
        raise FileNotFoundError(f"LoRA adapter not found: {lora_path}")

    print("[local] clearing GPU before CPU merge ...")
    _clear_cuda()
    _ram_note("before merge")
    print(
        "[local] WARNING: 27B FP16 ≈ 54GB. With 32GB DDR5 you need a large Windows pagefile "
        "(set virtual memory to ≥64GB on a fast SSD). Merge will be slow but should complete."
    )

    # Force everything off GPU so VRAM doesn't steal from system RAM mapping.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

    print(f"[local] loading LoRA for CPU merge from {lora_path}")
    offload = _offload_folder(args.output_dir)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(lora_path),
        max_seq_length=min(args.max_seq_length, 512),
        dtype=None,
        load_in_4bit=False,
        device_map="cpu",
        offload_folder=str(offload),
        max_memory={"cpu": "28GiB"},
    )
    FastLanguageModel.for_inference(model)
    _ram_note("after load (pre-merge)")

    merged_path.mkdir(parents=True, exist_ok=True)
    print(f"[local] merging → {merged_path} (FP16, CPU, sharded)")
    # max_shard_size keeps peak RAM lower than one giant file.
    model.save_pretrained_merged(
        str(merged_path),
        tokenizer,
        save_method="merged_16bit",
    )
    tokenizer.save_pretrained(str(merged_path))
    print(f"[local] merged FP16 saved at {merged_path}")

    del model
    _clear_cuda()
    _ram_note("after merge")


def export_gguf(args: argparse.Namespace) -> None:
    """Quantize merged FP16 → IQ2_XS GGUF."""
    merged_path = args.output_dir / MERGED_DIR
    gguf_path = args.output_dir / GGUF_DIR
    if not merged_path.is_dir():
        raise FileNotFoundError(f"Merged FP16 not found: {merged_path}")

    print("[local] clearing GPU before GGUF export ...")
    _clear_cuda()
    # Allow GPU again if Unsloth wants it for convert helpers; keep low footprint.
    os.environ.pop("CUDA_VISIBLE_DEVICES", None)

    print(f"[local] loading merged FP16 from {merged_path} (CPU-first)")
    offload = _offload_folder(args.output_dir)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(merged_path),
        max_seq_length=min(args.max_seq_length, 512),
        dtype=None,
        load_in_4bit=False,
        device_map="cpu",
        offload_folder=str(offload),
        max_memory={"cpu": "28GiB"},
    )
    FastLanguageModel.for_inference(model)

    gguf_path.mkdir(parents=True, exist_ok=True)
    print(f"[local] exporting GGUF quant={args.gguf_quant} → {gguf_path}")
    raw = str(args.imatrix_file).strip().lower()
    if raw in ("true", "1", "yes"):
        imatrix: bool | str = True
    elif raw in ("false", "0", "no", "none", ""):
        imatrix = False
    else:
        imatrix = args.imatrix_file
    print(f"[local] imatrix_file={imatrix!r}")
    model.save_pretrained_gguf(
        str(gguf_path),
        tokenizer,
        quantization_method=args.gguf_quant,
        imatrix_file=imatrix,
    )
    print(f"[local] GGUF done: {gguf_path}")
    del model
    _clear_cuda()


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Local 5070 Ti 16GB: Qwen3.8-27B NF4 → FP16 → IQ2_XS"
    )
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--dataset", type=Path, default=DATASET_PATH)
    ap.add_argument("--output_dir", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--max_seq_length", type=int, default=MAX_SEQ_LENGTH)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch_size", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=16)
    ap.add_argument("--lr", type=float, default=5e-6)
    ap.add_argument("--lora_r", type=int, default=16)
    ap.add_argument("--lora_alpha", type=int, default=32)
    ap.add_argument(
        "--lora_mlp",
        action="store_true",
        help="Also LoRA MLP (gate/up/down). Default off — saves VRAM on 16GB.",
    )
    ap.add_argument("--warmup_ratio", type=float, default=0.03)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--max_steps", type=int, default=-1)
    ap.add_argument("--save_steps", type=int, default=50)
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Shuffle + trainer seed. Change for a different data mix on continue runs.",
    )
    ap.add_argument("--resume_from_checkpoint", default=None)
    ap.add_argument("--gguf_quant", default="iq2_xs")
    ap.add_argument(
        "--imatrix_file",
        default="true",
        help="IQ* importance matrix: 'true' = Unsloth upstream, or path to .dat file",
    )
    ap.add_argument("--no_wandb", action="store_true")
    ap.add_argument(
        "--offload_gc",
        action="store_true",
        help="Explicit Unsloth CPU GC (already default on this script).",
    )

    stage = ap.add_mutually_exclusive_group()
    stage.add_argument("--train_only", action="store_true")
    stage.add_argument("--merge_only", action="store_true")
    stage.add_argument("--export_gguf_only", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(f"[local] output_dir={args.output_dir}")
    print("[local] target: RTX 5070 Ti 16GB + 32GB DDR5")
    _vram_note("start")
    _ram_note("start")

    if args.export_gguf_only:
        export_gguf(args)
        return

    if args.merge_only:
        merge_fp16_cpu(args)
        return

    model, tokenizer = train_qlora(args)
    del model, tokenizer
    _clear_cuda()

    if args.train_only:
        print("[local] train_only — skip merge/export")
        print(f"[local] LoRA at {args.output_dir / LORA_DIR}")
        return

    # Fresh process is cleaner for merge (CUDA_VISIBLE_DEVICES=""), but same-process works
    # if we clear first. Prefer: run --merge_only in a new terminal after train_only.
    merge_fp16_cpu(args)
    export_gguf(args)
    print(f"[local] pipeline complete → {args.output_dir}")


if __name__ == "__main__":
    main()
