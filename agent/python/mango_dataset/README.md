# Mango SFT 10.000 Dataset

Primary: **`../../datasets/mango_sft_10000.jsonl`**

See [`datasets/README.md`](../../datasets/README.md) for build pipeline, validation, and Unsloth loading.

```powershell
python datasets/build_language.py all
python datasets/merge_chunks_10000.py
pytest agent/python/mango_dataset/tests/test_mango_dataset.py
```

Legacy copies: `mango_sft_1000.jsonl`, `mango_sft_2000.jsonl`.
