# Mango SWE-bench

- Created: 2026-08-29T19:45:20.791284+00:00
- Dataset: `lite` (test)
- Model: `mango-local`
- Instances: 13
- Non-empty patches: 10 (76.9%)
- Reasoning cycles: 70
- Total tokens: 1294135
- Total time: 10206.4471s
- Predictions: `.mango\swebench_runs\lite50_predictions.json`

| Instance | Repo | Patch | Resolved | Iters | Reason | Tokens | Time s | Bucket |
|---|---|---|---|---:|---:|---:|---:|---|
| django__django-15814 | django/django | yes | — | 10 | 3 | 66100 | 701.9367 | patched |
| django__django-13401 | django/django | no | — | 24 | 2 | 123630 | 509.0198 | runtime_error |
| astropy__astropy-14995 | astropy/astropy | yes | — | 16 | 6 | 154736 | 582.6413 | patched |
| django__django-12308 | django/django | no | — | 14 | 2 | 63906 | 1791.593 | runtime_error |
| sphinx-doc__sphinx-7738 | sphinx-doc/sphinx | no | — | 24 | 1 | 106599 | 723.4624 | runtime_error |
| django__django-15996 | django/django | yes | — | 8 | 6 | 38430 | 495.1612 | patched |
| sympy__sympy-21171 | sympy/sympy | yes | — | 18 | 6 | 204544 | 1215.0079 | patched |
| sympy__sympy-20154 | sympy/sympy | yes | — | 24 | 16 | 136051 | 1230.2984 | patched |
| django__django-13551 | django/django | yes | — | 14 | 4 | 60949 | 491.3454 | patched |
| django__django-15252 | django/django | yes | — | 11 | 4 | 114638 | 455.0574 | patched |
| django__django-15851 | django/django | yes | — | 11 | 9 | 52871 | 344.0917 | patched |
| pallets__flask-5063 | pallets/flask | yes | — | 11 | 2 | 48826 | 480.7027 | patched |
| pytest-dev__pytest-7373 | pytest-dev/pytest | yes | — | 21 | 9 | 122855 | 1186.1292 | patched |

## Failure Buckets

- `patched`: 10
- `runtime_error`: 3

## Empty patches

- `django__django-13401` stop=`max_iterations`
  - error: No non-empty git diff after agent run (empty patch).
- `django__django-12308` stop=`timeout`
  - error: No non-empty git diff after agent run (empty patch).
- `sphinx-doc__sphinx-7738` stop=`max_iterations`
  - error: No non-empty git diff after agent run (empty patch).
