#!/usr/bin/env python3
"""
Fine-tune Qwen2.5-Coder-14B-Instruct with Unsloth (4-bit QLoRA).

Usage:
    pip install -r requirements.txt
    python finetune_qwen_coder.py                         # defaults
    python finetune_qwen_coder.py --epochs 1 --lr 5e-5    # override
    python finetune_qwen_coder.py --resume_from_checkpoint latest
"""

from __future__ import annotations

import argparse
import json
import os
import site
import sys
from pathlib import Path


def _configure_windows_triton_cc() -> None:
    """Point Triton at bundled TinyCC when packages live in user site-packages.

    triton-windows looks for tcc.exe under sysconfig platlib (system site-packages).
    With a user install that path misses; training then dies with 'Failed to find C compiler'.
    """
    if os.name != "nt" or os.environ.get("CC"):
        return
    candidates = []
    for root in (site.getusersitepackages(), *site.getsitepackages()):
        candidates.append(Path(root) / "triton" / "runtime" / "tcc" / "tcc.exe")
    for tcc in candidates:
        if tcc.is_file():
            os.environ["CC"] = str(tcc)
            print(f"Unsloth/Windows: using Triton CC={tcc}")
            return


def _patch_datasets_pickle_py314() -> None:
    """Python 3.14 changed pickle.Pickler._batch_setitems(items, obj).

    HuggingFace datasets <4.4 still overrides it with a 1-arg signature and
    crashes on Dataset creation. Unsloth currently pins datasets<4.4, so we
    patch locally instead of upgrading past their pin.
    """
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

# Force WandB off before HF/Unsloth import side-effects can prompt.
if "--no_wandb" in sys.argv:
    os.environ["WANDB_DISABLED"] = "true"
    os.environ["WANDB_MODE"] = "disabled"

# Avoid Unsloth activation CPU↔GPU ping-pong unless --offload_gc is requested.
if "--offload_gc" not in sys.argv:
    os.environ.setdefault("UNSLOTH_DISABLE_DOUBLE_BUFFER", "1")

# Reduce CUDA allocator fragmentation on a nearly-full 16GB card.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from unsloth import FastLanguageModel
from unsloth.chat_templates import train_on_responses_only
from trl import SFTTrainer, SFTConfig
from datasets import Dataset

MODEL_NAME = "unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit"
# 14B 4-bit already ~9–10GB; RTX 5070 Ti 16GB cannot hold bs=2 @ 1024 without thrashing.
MAX_SEQ_LENGTH = 768
DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "mango_sft_10000.jsonl"
OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "qwen-coder-14b-mango"


def load_and_format(path: Path, tok) -> list[str]:
    """Load JSONL, apply chat template, return list of formatted strings."""
    texts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        text = tok.apply_chat_template(
            row["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        texts.append(text)
    return texts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--dataset", type=Path, default=DATASET_PATH)
    ap.add_argument("--output_dir", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--max_seq_length", type=int, default=MAX_SEQ_LENGTH)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch_size", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=8)
    # Template-heavy SFT memorizes format fast at 1e-4; 5e-5 is safer for mango rows.
    ap.add_argument("--lr", type=float, default=9e-6)
    ap.add_argument("--lora_r", type=int, default=16)
    ap.add_argument("--lora_alpha", type=int, default=32)
    ap.add_argument("--warmup_ratio", type=float, default=0.03)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument(
        "--max_steps",
        type=int,
        default=-1,
        help="Cap steps (e.g. 800). -1 = full epoch(s). Useful when loss collapses early.",
    )
    ap.add_argument("--resume_from_checkpoint", default=None)
    ap.add_argument("--no_wandb", action="store_true")
    ap.add_argument(
        "--train_on_responses_only",
        action="store_true",
        help="Compute loss only on assistant response tokens (reduces format memorization).",
    )
    ap.add_argument("--save_gguf", action="store_true", help="Export Q4_K_M GGUF after training")
    ap.add_argument(
        "--offload_gc",
        action="store_true",
        help="Use Unsloth CPU-offloaded gradient checkpointing (slower on Windows, saves VRAM)",
    )
    args = ap.parse_args()

    # ----- Load model -----
    print(f"Loading {args.model} (4-bit) ...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    # "unsloth" GC offloads activations to RAM each layer — catastrophic on Windows PCIe.
    # Default True keeps activations on GPU (needs the shorter max_seq_length above).
    gc_mode = "unsloth" if args.offload_gc else True
    print(f"Gradient checkpointing: {gc_mode!r} | max_seq={args.max_seq_length} | bs={args.batch_size}")
    import torch
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        print(f"VRAM before LoRA: {(total-free)/1e9:.1f}/{(total)/1e9:.1f} GB used")

    # ----- LoRA adapters -----
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            # Drop MLP LoRA on 16GB — big VRAM win, small quality hit for SFT.
            # "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing=gc_mode,
        random_state=42,
    )

    # ----- Dataset -----
    print(f"Loading dataset from {args.dataset} ...")
    texts = load_and_format(args.dataset, tokenizer)
    print(f"Dataset: {len(texts)} examples, sample length: {len(texts[0])} chars")
    ds = Dataset.from_dict({"text": texts})

    # ----- Trainer -----
    args.output_dir.mkdir(parents=True, exist_ok=True)

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
        save_steps=100,
        save_total_limit=6,
        report_to="none",
        seed=42,
        dataloader_num_workers=0,
        dataloader_pin_memory=True,
        group_by_length=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds,
        args=training_args,
    )

    # Mask system+user tokens in loss — only train on assistant responses
    if args.train_on_responses_only:
        print("lol")
        # trainer = train_on_responses_only(
        #     trainer,
        #     instruction_part="<|im_start|>user\n",
        #     response_part="<|im_start|>assistant\n",
        # )

    # ----- Train -----
    print("Starting training ...")
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    # ----- Save -----
    print("Saving LoRA adapter ...")
    model.save_pretrained(str(args.output_dir / "lora"))
    tokenizer.save_pretrained(str(args.output_dir / "lora"))

    print("Saving merged 16-bit model ...")
    model.save_pretrained_merged(
        str(args.output_dir / "merged_16bit"),
        tokenizer,
        save_method="merged_16bit",
    )

    if args.save_gguf:
        print("Exporting GGUF (Q4_K_M) ...")
        model.save_pretrained_gguf(
            str(args.output_dir / "gguf"),
            tokenizer,
            quantization_method="q4_k_m",
        )

    print(f"Done. Output at {args.output_dir}")


if __name__ == "__main__":
    main()
