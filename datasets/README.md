# Mango SFT 10.000 Dataset

**Primary file:** `mango_sft_10000.jsonl` — 10.000 unique training rows, Unsloth `messages` format.

Legacy: `mango_sft_1000.jsonl`, `mango_sft_2000.jsonl` (unchanged snapshots).

## Composition

| Source | Rows | Description |
|--------|-----:|-------------|
| `chunks/` (v1) | 1000 | Hand-authored Python-heavy baseline |
| `chunks_v3/` | 9000 | Catalog-driven, multi-language, security-aware |
| **Total** | **10000** | |

### v3 language split (9000)

| Language | Rows |
|----------|-----:|
| Python | 2300 |
| JavaScript/TypeScript | 2000 |
| C++ | 2000 |
| C | 1500 |
| Rust | 900 |
| Go | 300 |

### Workflow mix (v3, approximate)

- test_fail_fix 35%
- security_review 15%
- multi_file_refactor 10%
- ambiguous_ask_epistemic 5%
- cot_cycle 17%
- epistemic_api 15%
- agent_finish 3%

## Build pipeline

```powershell
# Pilot (~100 rows, gate before scale)
python datasets/build_language.py pilot

# Per language (or all)
python datasets/build_language.py python
python datasets/build_language.py all

# Format validation
python datasets/builders/validate.py datasets/chunks_v3/python/python.jsonl

# Merge v1 + v3
python datasets/merge_chunks_10000.py
```

## Validation

1. **Format** — `datasets/builders/validate.py` (JSON shape, uniqueness, sentence counts)
2. **Content** — `datasets/builders/verify.py` (compile checks, security sandbox, hard-pair coherence)
3. **Tests** — `pytest agent/python/mango_dataset/tests/test_mango_dataset.py`

Sidecar metadata: `datasets/catalog/index.jsonl` (not in training JSONL).

## Prompts (single source of truth)

- Agent: `prompts/agent.md`
- Security audit: `prompts/security_review.md`
- CoT: embedded template (see v1 `chunks/cot.jsonl`)
- Epistemic: `prompts/epistemic.md`

## Prerequisites for verify.py

- Python 3 (ast.parse, pytest)
- Optional: gcc/g++, rustc, go, node, tsc for compile checks

## Unsloth

```python
dataset = load_dataset("json", data_files="datasets/mango_sft_10000.jsonl", split="train")
```

## Deprecated

- `build_chunks2.py` / `chunks2/` — replaced by `chunks_v3/` + catalog pipeline
- `merge_chunks_2000.py` — superseded by `merge_chunks_10000.py`
