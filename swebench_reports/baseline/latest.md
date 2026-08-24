# Mango SWE-bench

- Created: 2026-08-24T11:23:03.222996+00:00
- Dataset: `lite` (test)
- Model: `mango-local`
- Instances: 1
- Non-empty patches: 0 (0.0%)
- Reasoning cycles: 3
- Total tokens: 30948
- Total time: 87.9763s
- Predictions: `C:\Users\mikaj\Desktop\DevDeck\.mango\swebench_runs\predictions.json`

| Instance | Repo | Patch | Resolved | Iters | Reason | Tokens | Time s | Bucket |
|---|---|---|---|---:|---:|---:|---:|---|
| pylint-dev__pylint-5859 | pylint-dev/pylint | no | — | 8 | 3 | 30948 | 87.9763 | empty_other |

## Failure Buckets

- `empty_other`: 1

## Empty patches

- `pylint-dev__pylint-5859` stop=`error`
  - error: Tests never passed within iteration limit.
