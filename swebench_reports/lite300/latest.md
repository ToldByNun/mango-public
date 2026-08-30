# Mango SWE-bench

- Created: 2026-08-25T14:29:48.930286+00:00
- Dataset: `lite` (test)
- Model: `mango-local`
- Instances: 300
- Non-empty patches: 109 (36.3%)
- Reasoning cycles: 982
- Total tokens: 11969078
- Total time: 66003.7472s
- Predictions: `C:\Users\mikaj\Desktop\DevDeck\.mango\swebench_runs\predictions.json`

| Instance | Repo | Patch | Resolved | Iters | Reason | Tokens | Time s | Bucket |
|---|---|---|---|---:|---:|---:|---:|---|
| django__django-15814 | django/django | no | — | 8 | 3 | 43243 | 496.3631 | empty_other |
| django__django-13401 | django/django | no | — | 8 | 1 | 28015 | 211.9476 | empty_other |
| astropy__astropy-14995 | astropy/astropy | yes | — | 0 | 0 | 61984 | 190.927 | runtime_error |
| django__django-12308 | django/django | no | — | 7 | 6 | 35867 | 509.2582 | empty_other |
| sphinx-doc__sphinx-7738 | sphinx-doc/sphinx | no | — | 8 | 1 | 27018 | 87.5785 | empty_other |
| django__django-15996 | django/django | yes | — | 8 | 3 | 28311 | 170.6322 | patched |
| sympy__sympy-21171 | sympy/sympy | no | — | 8 | 5 | 82178 | 294.1131 | empty_other |
| sympy__sympy-20154 | sympy/sympy | no | — | 8 | 9 | 35526 | 280.3618 | empty_other |
| django__django-13551 | django/django | no | — | 8 | 4 | 28960 | 228.6055 | empty_other |
| django__django-15252 | django/django | no | — | 8 | 2 | 69130 | 333.2428 | empty_other |
| django__django-15851 | django/django | yes | — | 8 | 8 | 32655 | 278.5574 | patched |
| pallets__flask-5063 | pallets/flask | no | — | 8 | 10 | 42389 | 360.5192 | verification_failed |
| pytest-dev__pytest-7373 | pytest-dev/pytest | yes | — | 8 | 2 | 32560 | 447.234 | patched |
| sympy__sympy-23117 | sympy/sympy | yes | — | 0 | 0 | 34704 | 236.926 | runtime_error |
| sympy__sympy-13895 | sympy/sympy | no | — | 8 | 2 | 37508 | 214.6049 | empty_other |
| pydata__xarray-4094 | pydata/xarray | no | — | 0 | 0 | 39759 | 144.794 | runtime_error |
| psf__requests-2148 | psf/requests | yes | — | 8 | 8 | 45911 | 202.1557 | patched |
| django__django-11133 | django/django | no | — | 8 | 3 | 31624 | 197.6309 | empty_other |
| scikit-learn__scikit-learn-11281 | scikit-learn/scikit-learn | no | — | 8 | 8 | 38082 | 251.9533 | empty_other |
| sphinx-doc__sphinx-8627 | sphinx-doc/sphinx | yes | — | 8 | 2 | 34316 | 102.1415 | patched |
| matplotlib__matplotlib-26020 | matplotlib/matplotlib | yes | — | 8 | 3 | 148552 | 269.6691 | patched |
| django__django-14787 | django/django | no | — | 8 | 4 | 31606 | 284.8658 | empty_other |
| mwaskom__seaborn-2848 | mwaskom/seaborn | yes | — | 8 | 5 | 40209 | 494.5296 | patched |
| matplotlib__matplotlib-23563 | matplotlib/matplotlib | no | — | 0 | 0 | 0 | 7.3871 | runtime_error |
| django__django-16527 | django/django | no | — | 8 | 3 | 30996 | 206.2797 | empty_other |
| django__django-13028 | django/django | yes | — | 0 | 0 | 23091 | 91.345 | runtime_error |
| django__django-14752 | django/django | no | — | 8 | 4 | 41672 | 253.7023 | empty_other |
| scikit-learn__scikit-learn-10297 | scikit-learn/scikit-learn | no | — | 8 | 3 | 37172 | 217.5793 | bad_edit_anchor |
| django__django-16873 | django/django | yes | — | 8 | 2 | 35053 | 602.5288 | patched |
| sympy__sympy-24909 | sympy/sympy | no | — | 8 | 4 | 38603 | 145.2587 | empty_other |
| sympy__sympy-23262 | sympy/sympy | no | — | 8 | 1 | 35038 | 157.9821 | empty_other |
| django__django-14730 | django/django | no | — | 8 | 3 | 31951 | 231.2893 | empty_other |
| django__django-13768 | django/django | no | — | 8 | 3 | 29983 | 233.7579 | empty_other |
| matplotlib__matplotlib-25332 | matplotlib/matplotlib | no | — | 8 | 11 | 36882 | 220.38 | empty_other |
| pytest-dev__pytest-11143 | pytest-dev/pytest | yes | — | 8 | 6 | 80654 | 255.586 | patched |
| django__django-14017 | django/django | yes | — | 0 | 0 | 34561 | 195.0069 | runtime_error |
| sympy__sympy-20049 | sympy/sympy | no | — | 8 | 3 | 42583 | 135.8598 | empty_other |
| sympy__sympy-21614 | sympy/sympy | no | — | 8 | 3 | 30693 | 194.4998 | empty_other |
| sphinx-doc__sphinx-8474 | sphinx-doc/sphinx | no | — | 5 | 3 | 38884 | 425.1681 | empty_other |
| sympy__sympy-23191 | sympy/sympy | no | — | 8 | 5 | 42483 | 202.7632 | empty_other |
| sympy__sympy-22714 | sympy/sympy | no | — | 8 | 5 | 41530 | 273.38 | empty_other |
| astropy__astropy-14365 | astropy/astropy | yes | — | 8 | 7 | 51287 | 264.0597 | patched |
| django__django-16400 | django/django | yes | — | 8 | 8 | 85032 | 368.6125 | patched |
| matplotlib__matplotlib-24149 | matplotlib/matplotlib | yes | — | 0 | 0 | 30842 | 93.3705 | runtime_error |
| sympy__sympy-18835 | sympy/sympy | yes | — | 8 | 6 | 45268 | 250.9404 | patched |
| django__django-15400 | django/django | no | — | 8 | 7 | 40467 | 311.8303 | empty_other |
| sphinx-doc__sphinx-11445 | sphinx-doc/sphinx | no | — | 8 | 3 | 35882 | 120.957 | empty_other |
| django__django-11999 | django/django | no | — | 8 | 1 | 42426 | 213.3296 | empty_other |
| django__django-12708 | django/django | no | — | 6 | 6 | 35215 | 516.9493 | empty_other |
| django__django-11179 | django/django | yes | — | 8 | 3 | 33648 | 426.4913 | patched |
| pylint-dev__pylint-7080 | pylint-dev/pylint | no | — | 8 | 3 | 165920 | 308.1547 | empty_other |
| sympy__sympy-20639 | sympy/sympy | no | — | 8 | 4 | 40468 | 324.0576 | empty_other |
| scikit-learn__scikit-learn-13241 | scikit-learn/scikit-learn | yes | — | 8 | 4 | 88053 | 360.4979 | patched |
| pytest-dev__pytest-8906 | pytest-dev/pytest | no | — | 8 | 2 | 44354 | 850.2864 | empty_other |
| django__django-17051 | django/django | yes | — | 0 | 0 | 25096 | 117.6368 | runtime_error |
| scikit-learn__scikit-learn-15512 | scikit-learn/scikit-learn | no | — | 8 | 1 | 33527 | 103.3919 | empty_other |
| sympy__sympy-17630 | sympy/sympy | yes | — | 0 | 0 | 24378 | 103.2444 | runtime_error |
| sympy__sympy-11897 | sympy/sympy | no | — | 7 | 1 | 40276 | 479.2553 | empty_other |
| django__django-12747 | django/django | no | — | 8 | 5 | 34099 | 241.2679 | empty_other |
| psf__requests-2674 | psf/requests | no | — | 8 | 9 | 68537 | 615.2726 | empty_other |
| django__django-16046 | django/django | yes | — | 0 | 0 | 24884 | 109.1738 | runtime_error |
| sympy__sympy-15011 | sympy/sympy | no | — | 8 | 7 | 39239 | 196.7477 | empty_other |
| django__django-11848 | django/django | no | — | 8 | 3 | 40262 | 259.3964 | empty_other |
| django__django-14999 | django/django | no | — | 8 | 1 | 26382 | 165.7534 | empty_other |
| django__django-11422 | django/django | yes | — | 0 | 0 | 41339 | 233.1131 | runtime_error |
| sympy__sympy-16281 | sympy/sympy | no | — | 8 | 4 | 37131 | 141.3893 | empty_other |
| sympy__sympy-15345 | sympy/sympy | yes | — | 0 | 0 | 19073 | 99.8046 | runtime_error |
| django__django-14915 | django/django | no | — | 5 | 4 | 26817 | 405.119 | empty_other |
| sphinx-doc__sphinx-8506 | sphinx-doc/sphinx | no | — | 8 | 8 | 57122 | 279.7488 | empty_other |
| scikit-learn__scikit-learn-10508 | scikit-learn/scikit-learn | no | — | 8 | 4 | 43186 | 212.1445 | empty_other |
| sympy__sympy-14024 | sympy/sympy | no | — | 8 | 4 | 35062 | 150.1546 | empty_other |
| django__django-12453 | django/django | yes | — | 0 | 0 | 24286 | 110.525 | runtime_error |
| sympy__sympy-21847 | sympy/sympy | yes | — | 0 | 0 | 32307 | 120.0234 | runtime_error |
| matplotlib__matplotlib-18869 | matplotlib/matplotlib | no | — | 8 | 4 | 35929 | 161.8191 | empty_other |
| django__django-12856 | django/django | yes | — | 0 | 0 | 37615 | 179.1816 | runtime_error |
| django__django-11039 | django/django | no | — | 8 | 2 | 31796 | 167.2681 | empty_other |
| django__django-13590 | django/django | yes | — | 8 | 8 | 39306 | 289.5023 | patched |
| django__django-15347 | django/django | no | — | 8 | 4 | 33930 | 228.0124 | empty_other |
| sympy__sympy-21612 | sympy/sympy | yes | — | 0 | 0 | 21124 | 66.3015 | runtime_error |
| django__django-11620 | django/django | yes | — | 0 | 0 | 26519 | 493.972 | runtime_error |
| django__django-15781 | django/django | yes | — | 8 | 10 | 59211 | 304.4387 | patched |
| sympy__sympy-12236 | sympy/sympy | yes | — | 8 | 12 | 91521 | 338.0535 | patched |
| sympy__sympy-18698 | sympy/sympy | yes | — | 0 | 0 | 61958 | 279.8857 | runtime_error |
| pytest-dev__pytest-7168 | pytest-dev/pytest | yes | — | 0 | 0 | 72421 | 122.8542 | runtime_error |
| django__django-12700 | django/django | yes | — | 0 | 0 | 18775 | 75.7901 | runtime_error |
| django__django-13933 | django/django | yes | — | 6 | 2 | 29886 | 131.2957 | patched |
| pydata__xarray-5131 | pydata/xarray | no | — | 8 | 3 | 42358 | 144.2297 | empty_other |
| sympy__sympy-12481 | sympy/sympy | no | — | 8 | 4 | 30758 | 175.2142 | empty_other |
| django__django-15213 | django/django | no | — | 8 | 3 | 33309 | 165.2175 | empty_other |
| sympy__sympy-22005 | sympy/sympy | yes | — | 5 | 2 | 29233 | 108.2271 | patched |
| astropy__astropy-14182 | astropy/astropy | no | — | 8 | 3 | 36143 | 141.3389 | empty_other |
| sympy__sympy-15308 | sympy/sympy | yes | — | 8 | 2 | 31811 | 306.8107 | patched |
| pytest-dev__pytest-5227 | pytest-dev/pytest | no | — | 8 | 4 | 24927 | 224.4017 | empty_other |
| matplotlib__matplotlib-23964 | matplotlib/matplotlib | no | — | 8 | 1 | 43137 | 82.7154 | empty_other |
| django__django-17087 | django/django | yes | — | 0 | 0 | 37984 | 149.9747 | runtime_error |
| matplotlib__matplotlib-25079 | matplotlib/matplotlib | no | — | 8 | 7 | 53968 | 287.3129 | empty_other |
| sympy__sympy-16503 | sympy/sympy | yes | — | 0 | 0 | 22703 | 89.767 | runtime_error |
| django__django-14016 | django/django | no | — | 8 | 5 | 31036 | 211.233 | empty_other |
| pylint-dev__pylint-6506 | pylint-dev/pylint | yes | — | 0 | 0 | 19243 | 67.9603 | runtime_error |
| django__django-15902 | django/django | no | — | 8 | 10 | 43005 | 265.8303 | empty_other |
| scikit-learn__scikit-learn-14894 | scikit-learn/scikit-learn | no | — | 8 | 4 | 32354 | 727.322 | empty_other |
| django__django-16139 | django/django | no | — | 8 | 4 | 34326 | 229.2142 | empty_other |
| sympy__sympy-12419 | sympy/sympy | yes | — | 8 | 6 | 88464 | 275.4932 | patched |
| matplotlib__matplotlib-23299 | matplotlib/matplotlib | no | — | 7 | 6 | 48356 | 447.4627 | empty_other |
| sphinx-doc__sphinx-8713 | sphinx-doc/sphinx | no | — | 8 | 1 | 29456 | 82.9982 | empty_other |
| django__django-11910 | django/django | no | — | 8 | 3 | 30217 | 165.9628 | empty_other |
| django__django-15202 | django/django | no | — | 8 | 3 | 32165 | 223.6633 | empty_other |
| django__django-16910 | django/django | no | — | 8 | 2 | 32602 | 167.5557 | empty_other |
| pytest-dev__pytest-7220 | pytest-dev/pytest | no | — | 8 | 13 | 46310 | 279.2047 | empty_other |
| django__django-14411 | django/django | no | — | 8 | 6 | 29311 | 227.4628 | empty_other |
| scikit-learn__scikit-learn-10949 | scikit-learn/scikit-learn | no | — | 8 | 3 | 34711 | 122.3306 | empty_other |
| scikit-learn__scikit-learn-13142 | scikit-learn/scikit-learn | no | — | 8 | 1 | 41348 | 96.4996 | empty_other |
| django__django-15498 | django/django | no | — | 8 | 3 | 26845 | 122.3005 | empty_other |
| django__django-12983 | django/django | no | — | 8 | 6 | 33151 | 250.3185 | empty_other |
| scikit-learn__scikit-learn-15535 | scikit-learn/scikit-learn | no | — | 5 | 2 | 26180 | 433.1098 | empty_other |
| sympy__sympy-24102 | sympy/sympy | no | — | 7 | 1 | 32768 | 402.0473 | empty_other |
| sympy__sympy-20442 | sympy/sympy | yes | — | 0 | 0 | 44514 | 116.9618 | runtime_error |
| django__django-15320 | django/django | no | — | 8 | 7 | 35724 | 206.5013 | empty_other |
| django__django-11099 | django/django | yes | — | 8 | 2 | 28110 | 206.7922 | patched |
| django__django-14667 | django/django | no | — | 8 | 3 | 54219 | 259.7496 | empty_other |
| scikit-learn__scikit-learn-25500 | scikit-learn/scikit-learn | yes | — | 8 | 3 | 57641 | 172.82 | patched |
| django__django-13658 | django/django | no | — | 8 | 8 | 41875 | 273.9188 | empty_other |
| django__django-13925 | django/django | no | — | 8 | 1 | 47805 | 175.4788 | empty_other |
| sympy__sympy-18087 | sympy/sympy | no | — | 8 | 4 | 49571 | 231.2804 | empty_other |
| mwaskom__seaborn-3190 | mwaskom/seaborn | no | — | 8 | 2 | 35770 | 104.463 | empty_other |
| scikit-learn__scikit-learn-12471 | scikit-learn/scikit-learn | no | — | 8 | 4 | 39024 | 161.8116 | empty_other |
| django__django-12915 | django/django | yes | — | 0 | 0 | 16716 | 73.2262 | runtime_error |
| sympy__sympy-13773 | sympy/sympy | yes | — | 8 | 7 | 36876 | 228.7339 | patched |
| sympy__sympy-19254 | sympy/sympy | no | — | 8 | 2 | 29278 | 206.8366 | empty_other |
| pytest-dev__pytest-6116 | pytest-dev/pytest | no | — | 6 | 4 | 40236 | 368.6061 | empty_other |
| scikit-learn__scikit-learn-25747 | scikit-learn/scikit-learn | yes | — | 0 | 0 | 45234 | 110.7292 | runtime_error |
| sympy__sympy-13043 | sympy/sympy | yes | — | 7 | 7 | 34133 | 196.0744 | patched |
| sympy__sympy-20590 | sympy/sympy | no | — | 8 | 1 | 30280 | 125.2828 | empty_other |
| django__django-16255 | django/django | yes | — | 0 | 0 | 18443 | 82.8743 | runtime_error |
| sympy__sympy-13971 | sympy/sympy | no | — | 8 | 3 | 29281 | 151.3431 | empty_other |
| pydata__xarray-4493 | pydata/xarray | no | — | 8 | 3 | 53081 | 95.0732 | empty_other |
| django__django-13321 | django/django | yes | — | 8 | 7 | 67799 | 282.5039 | patched |
| matplotlib__matplotlib-22835 | matplotlib/matplotlib | no | — | 8 | 5 | 90271 | 175.96 | empty_other |
| pytest-dev__pytest-5413 | pytest-dev/pytest | no | — | 8 | 2 | 49732 | 128.3942 | empty_other |
| sphinx-doc__sphinx-7975 | sphinx-doc/sphinx | no | — | 8 | 5 | 27502 | 189.6105 | empty_other |
| django__django-13220 | django/django | yes | — | 8 | 4 | 33035 | 210.2228 | patched |
| astropy__astropy-7746 | astropy/astropy | no | — | 8 | 17 | 55477 | 292.3555 | empty_other |
| scikit-learn__scikit-learn-14983 | scikit-learn/scikit-learn | yes | — | 8 | 4 | 44864 | 131.1532 | patched |
| pylint-dev__pylint-7228 | pylint-dev/pylint | no | — | 8 | 4 | 50749 | 113.5999 | empty_other |
| django__django-15695 | django/django | no | — | 8 | 5 | 41763 | 239.9023 | empty_other |
| sympy__sympy-11400 | sympy/sympy | yes | — | 7 | 2 | 30490 | 138.3857 | patched |
| scikit-learn__scikit-learn-13584 | scikit-learn/scikit-learn | no | — | 8 | 3 | 29257 | 123.7454 | empty_other |
| django__django-12125 | django/django | no | — | 8 | 8 | 57662 | 283.334 | empty_other |
| sphinx-doc__sphinx-8595 | sphinx-doc/sphinx | no | — | 8 | 1 | 25006 | 74.3553 | empty_other |
| sympy__sympy-19487 | sympy/sympy | no | — | 8 | 1 | 57291 | 102.1858 | empty_other |
| sympy__sympy-13437 | sympy/sympy | no | — | 8 | 1 | 25328 | 104.4064 | empty_other |
| django__django-10914 | django/django | yes | — | 0 | 0 | 43855 | 142.7035 | runtime_error |
| django__django-11583 | django/django | no | — | 8 | 2 | 59935 | 827.5315 | empty_other |
| matplotlib__matplotlib-25311 | matplotlib/matplotlib | no | — | 4 | 0 | 18037 | 353.2582 | empty_other |
| mwaskom__seaborn-3407 | mwaskom/seaborn | no | — | 8 | 6 | 48532 | 235.5943 | empty_other |
| django__django-11049 | django/django | no | — | 8 | 3 | 28833 | 135.5934 | empty_other |
| scikit-learn__scikit-learn-13497 | scikit-learn/scikit-learn | yes | — | 6 | 1 | 22913 | 80.452 | patched |
| sympy__sympy-20322 | sympy/sympy | yes | — | 0 | 0 | 87541 | 196.6486 | runtime_error |
| django__django-11905 | django/django | no | — | 8 | 1 | 42295 | 91.5059 | empty_other |
| django__django-11283 | django/django | yes | — | 0 | 0 | 30461 | 126.0097 | runtime_error |
| django__django-16379 | django/django | yes | — | 0 | 0 | 28472 | 179.4354 | runtime_error |
| sympy__sympy-17022 | sympy/sympy | no | — | 5 | 4 | 27076 | 415.5979 | empty_other |
| django__django-12908 | django/django | no | — | 8 | 3 | 31544 | 195.8118 | empty_other |
| django__django-15738 | django/django | no | — | 8 | 1 | 41594 | 146.383 | empty_other |
| django__django-13448 | django/django | yes | — | 8 | 3 | 63364 | 221.8284 | patched |
| scikit-learn__scikit-learn-13779 | scikit-learn/scikit-learn | no | — | 7 | 3 | 33953 | 381.335 | empty_other |
| django__django-14155 | django/django | no | — | 8 | 3 | 30008 | 242.2917 | empty_other |
| astropy__astropy-6938 | astropy/astropy | yes | — | 0 | 0 | 23761 | 88.3799 | runtime_error |
| django__django-13757 | django/django | no | — | 8 | 5 | 32685 | 183.2327 | empty_other |
| sphinx-doc__sphinx-8282 | sphinx-doc/sphinx | no | — | 8 | 2 | 22814 | 61.3251 | empty_other |
| sympy__sympy-13146 | sympy/sympy | no | — | 8 | 3 | 31085 | 114.6018 | empty_other |
| sympy__sympy-21055 | sympy/sympy | no | — | 8 | 8 | 36546 | 198.1457 | empty_other |
| scikit-learn__scikit-learn-11040 | scikit-learn/scikit-learn | no | — | 0 | 0 | 29950 | 164.3277 | runtime_error |
| sympy__sympy-16988 | sympy/sympy | no | — | 8 | 2 | 27737 | 88.9879 | empty_other |
| django__django-12113 | django/django | no | — | 8 | 3 | 47737 | 172.4153 | empty_other |
| sphinx-doc__sphinx-8273 | sphinx-doc/sphinx | yes | — | 8 | 4 | 35228 | 171.355 | patched |
| django__django-14997 | django/django | no | — | 8 | 3 | 55790 | 184.128 | empty_other |
| django__django-11742 | django/django | no | — | 8 | 2 | 25203 | 173.5463 | empty_other |
| django__django-15388 | django/django | no | — | 8 | 7 | 45886 | 226.1187 | empty_other |
| scikit-learn__scikit-learn-14092 | scikit-learn/scikit-learn | no | — | 8 | 2 | 51528 | 180.3938 | empty_other |
| pylint-dev__pylint-7114 | pylint-dev/pylint | no | — | 8 | 4 | 33066 | 110.958 | empty_other |
| sympy__sympy-20212 | sympy/sympy | yes | — | 8 | 4 | 31804 | 262.5906 | patched |
| matplotlib__matplotlib-23562 | matplotlib/matplotlib | yes | — | 8 | 3 | 66521 | 260.095 | patched |
| django__django-16820 | django/django | no | — | 8 | 3 | 31588 | 267.1507 | empty_other |
| scikit-learn__scikit-learn-13439 | scikit-learn/scikit-learn | yes | — | 8 | 5 | 40026 | 225.7194 | patched |
| pallets__flask-4992 | pallets/flask | no | — | 8 | 4 | 36682 | 133.6402 | empty_other |
| django__django-16229 | django/django | no | — | 8 | 4 | 37162 | 171.0316 | empty_other |
| sympy__sympy-18621 | sympy/sympy | yes | — | 0 | 0 | 22341 | 84.5004 | runtime_error |
| sphinx-doc__sphinx-8721 | sphinx-doc/sphinx | no | — | 5 | 2 | 23145 | 450.4641 | empty_other |
| django__django-13447 | django/django | no | — | 8 | 1 | 23059 | 140.2594 | empty_other |
| django__django-13660 | django/django | yes | — | 0 | 0 | 19871 | 86.685 | runtime_error |
| sympy__sympy-18199 | sympy/sympy | no | — | 8 | 7 | 31788 | 237.6813 | empty_other |
| django__django-14238 | django/django | no | — | 8 | 1 | 35274 | 161.7766 | empty_other |
| matplotlib__matplotlib-24970 | matplotlib/matplotlib | yes | — | 0 | 0 | 39044 | 136.5908 | runtime_error |
| sympy__sympy-13471 | sympy/sympy | yes | — | 5 | 2 | 23484 | 115.4427 | patched |
| django__django-15819 | django/django | no | — | 8 | 1 | 25455 | 192.9045 | empty_other |
| pytest-dev__pytest-5692 | pytest-dev/pytest | yes | — | 0 | 0 | 32943 | 110.6172 | runtime_error |
| sympy__sympy-13031 | sympy/sympy | no | — | 8 | 6 | 48548 | 317.2779 | empty_other |
| pytest-dev__pytest-7432 | pytest-dev/pytest | no | — | 8 | 2 | 29409 | 343.009 | empty_other |
| sympy__sympy-14396 | sympy/sympy | no | — | 8 | 3 | 42351 | 165.7696 | empty_other |
| django__django-11019 | django/django | yes | — | 8 | 4 | 101922 | 269.0677 | patched |
| django__django-12589 | django/django | no | — | 8 | 5 | 51372 | 295.3825 | empty_other |
| django__django-12286 | django/django | yes | — | 8 | 5 | 35175 | 233.3463 | patched |
| scikit-learn__scikit-learn-13496 | scikit-learn/scikit-learn | no | — | 4 | 1 | 20889 | 329.3319 | empty_other |
| pytest-dev__pytest-5495 | pytest-dev/pytest | no | — | 8 | 3 | 28321 | 74.0652 | empty_other |
| django__django-11797 | django/django | no | — | 8 | 3 | 44314 | 201.2785 | empty_other |
| django__django-11564 | django/django | no | — | 8 | 1 | 42304 | 136.8231 | empty_other |
| matplotlib__matplotlib-22711 | matplotlib/matplotlib | no | — | 0 | 0 | 41868 | 105.0893 | runtime_error |
| django__django-13964 | django/django | no | — | 8 | 4 | 43354 | 227.7761 | empty_other |
| pytest-dev__pytest-11148 | pytest-dev/pytest | no | — | 8 | 4 | 38919 | 112.0431 | empty_other |
| pydata__xarray-3364 | pydata/xarray | no | — | 8 | 5 | 32590 | 111.7706 | empty_other |
| django__django-11001 | django/django | no | — | 8 | 2 | 39706 | 128.4853 | empty_other |
| sympy__sympy-24213 | sympy/sympy | no | — | 8 | 2 | 31013 | 101.6301 | empty_other |
| sphinx-doc__sphinx-7686 | sphinx-doc/sphinx | no | — | 8 | 1 | 28631 | 88.1127 | empty_other |
| sympy__sympy-21379 | sympy/sympy | yes | — | 0 | 0 | 46873 | 87.2302 | runtime_error |
| sympy__sympy-18057 | sympy/sympy | no | — | 8 | 7 | 46202 | 227.4084 | empty_other |
| sympy__sympy-13480 | sympy/sympy | yes | — | 0 | 0 | 19928 | 88.6611 | runtime_error |
| sympy__sympy-15678 | sympy/sympy | no | — | 8 | 2 | 31662 | 351.8788 | empty_other |
| pallets__flask-4045 | pallets/flask | no | — | 8 | 5 | 29068 | 107.2149 | empty_other |
| sympy__sympy-14317 | sympy/sympy | no | — | 8 | 7 | 34530 | 196.023 | empty_other |
| django__django-15790 | django/django | no | — | 8 | 3 | 30766 | 306.2534 | empty_other |
| sympy__sympy-12454 | sympy/sympy | yes | — | 8 | 3 | 35964 | 249.7255 | patched |
| psf__requests-2317 | psf/requests | yes | — | 0 | 0 | 21383 | 69.9219 | runtime_error |
| sympy__sympy-24066 | sympy/sympy | yes | — | 7 | 6 | 32805 | 272.8772 | patched |
| sympy__sympy-16106 | sympy/sympy | yes | — | 0 | 0 | 24317 | 148.1351 | runtime_error |
| django__django-14534 | django/django | no | — | 8 | 4 | 36585 | 220.5925 | empty_other |
| psf__requests-1963 | psf/requests | no | — | 8 | 8 | 35169 | 149.3027 | empty_other |
| sympy__sympy-13177 | sympy/sympy | no | — | 8 | 3 | 33357 | 200.0048 | empty_other |
| psf__requests-3362 | psf/requests | yes | — | 6 | 1 | 26723 | 387.1783 | patched |
| sympy__sympy-17655 | sympy/sympy | yes | — | 8 | 5 | 39578 | 182.5008 | patched |
| django__django-13315 | django/django | no | — | 7 | 6 | 69593 | 632.1078 | empty_other |
| matplotlib__matplotlib-25433 | matplotlib/matplotlib | no | — | 6 | 3 | 46417 | 282.2095 | empty_other |
| sphinx-doc__sphinx-10451 | sphinx-doc/sphinx | no | — | 8 | 2 | 41276 | 100.9462 | empty_other |
| django__django-15061 | django/django | yes | — | 8 | 7 | 34600 | 220.2569 | patched |
| matplotlib__matplotlib-25498 | matplotlib/matplotlib | yes | — | 0 | 0 | 79547 | 181.0139 | runtime_error |
| sympy__sympy-18532 | sympy/sympy | yes | — | 7 | 3 | 41648 | 448.331 | patched |
| pytest-dev__pytest-7490 | pytest-dev/pytest | no | — | 8 | 2 | 104321 | 149.5837 | empty_other |
| django__django-14580 | django/django | yes | — | 0 | 0 | 25858 | 123.0609 | runtime_error |
| matplotlib__matplotlib-26011 | matplotlib/matplotlib | no | — | 8 | 4 | 84957 | 175.7729 | empty_other |
| django__django-14672 | django/django | yes | — | 0 | 0 | 57269 | 162.071 | runtime_error |
| django__django-11964 | django/django | no | — | 8 | 4 | 40756 | 128.6858 | empty_other |
| matplotlib__matplotlib-23476 | matplotlib/matplotlib | yes | — | 8 | 5 | 49990 | 320.9404 | patched |
| sympy__sympy-13647 | sympy/sympy | yes | — | 8 | 8 | 47586 | 215.5443 | patched |
| matplotlib__matplotlib-23987 | matplotlib/matplotlib | yes | — | 8 | 3 | 33534 | 444.6016 | patched |
| sympy__sympy-11870 | sympy/sympy | no | — | 8 | 1 | 29484 | 106.6062 | empty_other |
| django__django-14855 | django/django | yes | — | 0 | 0 | 29546 | 183.866 | runtime_error |
| sympy__sympy-24152 | sympy/sympy | yes | — | 8 | 10 | 46380 | 219.5422 | patched |
| django__django-11815 | django/django | yes | — | 0 | 0 | 24399 | 121.2803 | runtime_error |
| django__django-16816 | django/django | no | — | 8 | 3 | 60566 | 174.8001 | empty_other |
| matplotlib__matplotlib-25442 | matplotlib/matplotlib | no | — | 8 | 11 | 48086 | 246.7437 | empty_other |
| sympy__sympy-15609 | sympy/sympy | no | — | 7 | 4 | 32434 | 245.5198 | empty_other |
| django__django-12470 | django/django | no | — | 8 | 2 | 26601 | 145.8329 | empty_other |
| sympy__sympy-14774 | sympy/sympy | yes | — | 8 | 3 | 30012 | 123.5976 | patched |
| scikit-learn__scikit-learn-25638 | scikit-learn/scikit-learn | no | — | 5 | 0 | 25308 | 331.143 | empty_other |
| django__django-13710 | django/django | yes | — | 8 | 4 | 31579 | 195.3327 | patched |
| django__django-16595 | django/django | no | — | 8 | 2 | 32087 | 172.2054 | empty_other |
| django__django-15789 | django/django | yes | — | 0 | 0 | 21494 | 147.9022 | runtime_error |
| django__django-12284 | django/django | no | — | 8 | 4 | 47836 | 199.1075 | empty_other |
| pylint-dev__pylint-7993 | pylint-dev/pylint | no | — | 8 | 2 | 34150 | 108.0528 | empty_other |
| matplotlib__matplotlib-23314 | matplotlib/matplotlib | no | — | 8 | 3 | 34621 | 294.0833 | empty_other |
| pytest-dev__pytest-5221 | pytest-dev/pytest | no | — | 8 | 4 | 23033 | 83.8941 | empty_other |
| sympy__sympy-15346 | sympy/sympy | yes | — | 0 | 0 | 50371 | 219.6453 | runtime_error |
| astropy__astropy-12907 | astropy/astropy | no | — | 6 | 3 | 30187 | 335.9914 | empty_other |
| scikit-learn__scikit-learn-25570 | scikit-learn/scikit-learn | no | — | 8 | 4 | 59621 | 229.4265 | empty_other |
| django__django-13033 | django/django | yes | — | 0 | 0 | 33677 | 179.6281 | runtime_error |
| django__django-10924 | django/django | no | — | 8 | 12 | 74512 | 365.4532 | empty_other |
| django__django-12184 | django/django | no | — | 8 | 1 | 29464 | 173.4839 | empty_other |
| matplotlib__matplotlib-24334 | matplotlib/matplotlib | no | — | 8 | 5 | 35736 | 302.9901 | empty_other |
| sympy__sympy-18189 | sympy/sympy | yes | — | 0 | 0 | 48926 | 202.4186 | runtime_error |
| sympy__sympy-12171 | sympy/sympy | yes | — | 8 | 3 | 31487 | 218.1504 | patched |
| sympy__sympy-22840 | sympy/sympy | no | — | 8 | 9 | 117757 | 317.2691 | empty_other |
| django__django-16041 | django/django | no | — | 8 | 4 | 51164 | 272.2957 | empty_other |
| pylint-dev__pylint-5859 | pylint-dev/pylint | no | — | 8 | 1 | 23455 | 117.4798 | empty_other |
| sphinx-doc__sphinx-8801 | sphinx-doc/sphinx | no | — | 8 | 4 | 25752 | 189.4359 | empty_other |
| pytest-dev__pytest-8365 | pytest-dev/pytest | yes | — | 8 | 5 | 39083 | 372.3741 | patched |
| django__django-13265 | django/django | no | — | 8 | 1 | 34929 | 221.1171 | empty_other |
| sympy__sympy-13915 | sympy/sympy | no | — | 8 | 4 | 51875 | 251.2563 | empty_other |
| pytest-dev__pytest-5103 | pytest-dev/pytest | no | — | 8 | 4 | 34957 | 139.8668 | empty_other |
| django__django-12497 | django/django | no | — | 8 | 3 | 28773 | 221.829 | empty_other |
| django__django-13230 | django/django | yes | — | 8 | 3 | 28064 | 192.6834 | patched |
| pydata__xarray-4248 | pydata/xarray | no | — | 8 | 3 | 41324 | 142.6225 | empty_other |
| django__django-14608 | django/django | yes | — | 8 | 5 | 34285 | 234.3896 | patched |
| sympy__sympy-19007 | sympy/sympy | no | — | 8 | 4 | 35423 | 266.3226 | empty_other |
| matplotlib__matplotlib-23913 | matplotlib/matplotlib | no | — | 6 | 4 | 33682 | 526.9749 | empty_other |
| django__django-13158 | django/django | no | — | 8 | 2 | 30678 | 155.3531 | empty_other |
| sympy__sympy-21627 | sympy/sympy | no | — | 8 | 1 | 29279 | 93.8622 | empty_other |
| mwaskom__seaborn-3010 | mwaskom/seaborn | yes | — | 8 | 5 | 53281 | 284.0973 | patched |
| django__django-14382 | django/django | yes | — | 6 | 3 | 27306 | 160.069 | patched |
| sympy__sympy-16792 | sympy/sympy | no | — | 8 | 4 | 36694 | 236.493 | empty_other |
| django__django-16408 | django/django | yes | — | 0 | 0 | 36658 | 157.7605 | runtime_error |
| pytest-dev__pytest-9359 | pytest-dev/pytest | yes | — | 7 | 3 | 39838 | 95.2952 | patched |
| sympy__sympy-14308 | sympy/sympy | no | — | 0 | 0 | 36355 | 227.8964 | runtime_error |
| psf__requests-863 | psf/requests | yes | — | 8 | 4 | 33333 | 105.4354 | patched |
| sphinx-doc__sphinx-10325 | sphinx-doc/sphinx | no | — | 8 | 2 | 30965 | 87.1111 | empty_other |
| sympy__sympy-14817 | sympy/sympy | no | — | 7 | 10 | 50004 | 580.9817 | empty_other |
| sympy__sympy-17139 | sympy/sympy | no | — | 8 | 4 | 41979 | 278.0778 | empty_other |
| matplotlib__matplotlib-24265 | matplotlib/matplotlib | yes | — | 8 | 3 | 32173 | 164.6278 | patched |
| django__django-11630 | django/django | no | — | 8 | 1 | 29096 | 175.8751 | empty_other |
| sphinx-doc__sphinx-8435 | sphinx-doc/sphinx | yes | — | 8 | 3 | 31011 | 407.1181 | patched |
| scikit-learn__scikit-learn-14087 | scikit-learn/scikit-learn | yes | — | 8 | 5 | 51736 | 262.449 | patched |

## Failure Buckets

- `bad_edit_anchor`: 1
- `empty_other`: 184
- `patched`: 61
- `runtime_error`: 53
- `verification_failed`: 1

## Empty patches

- `django__django-15814` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13401` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12308` stop=`completed`
- `sphinx-doc__sphinx-7738` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-21171` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-20154` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13551` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15252` stop=`error`
  - error: Tests never passed within iteration limit.
- `pallets__flask-5063` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-13895` stop=`error`
  - error: Tests never passed within iteration limit.
- `pydata__xarray-4094` stop=`error`
  - error: 'prompts/feedback.md has no section #readonly_edit_now, #_note_thought_action_loop.readonly_edit_now'
- `django__django-11133` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-11281` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14787` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-23563` stop=`error`
  - error: Requested tokens (56369) exceed context window of 16384
- `django__django-16527` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14752` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-10297` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-24909` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-23262` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14730` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13768` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-25332` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-20049` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-21614` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-8474` stop=`completed`
- `sympy__sympy-23191` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-22714` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15400` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-11445` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11999` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12708` stop=`completed`
- `pylint-dev__pylint-7080` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-20639` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-8906` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-15512` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-11897` stop=`completed`
- `django__django-12747` stop=`error`
  - error: Tests never passed within iteration limit.
- `psf__requests-2674` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-15011` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11848` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14999` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-16281` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14915` stop=`completed`
- `sphinx-doc__sphinx-8506` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-10508` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-14024` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-18869` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11039` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15347` stop=`error`
  - error: Tests never passed within iteration limit.
- `pydata__xarray-5131` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-12481` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15213` stop=`error`
  - error: Tests never passed within iteration limit.
- `astropy__astropy-14182` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-5227` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-23964` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-25079` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14016` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15902` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-14894` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-16139` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-23299` stop=`completed`
- `sphinx-doc__sphinx-8713` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11910` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15202` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-16910` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-7220` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14411` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-10949` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-13142` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15498` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12983` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-15535` stop=`completed`
- `sympy__sympy-24102` stop=`completed`
- `django__django-15320` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14667` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13658` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13925` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-18087` stop=`error`
  - error: Tests never passed within iteration limit.
- `mwaskom__seaborn-3190` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-12471` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-19254` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-6116` stop=`completed`
- `sympy__sympy-20590` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-13971` stop=`error`
  - error: Tests never passed within iteration limit.
- `pydata__xarray-4493` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-22835` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-5413` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-7975` stop=`error`
  - error: Tests never passed within iteration limit.
- `astropy__astropy-7746` stop=`error`
  - error: Tests never passed within iteration limit.
- `pylint-dev__pylint-7228` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15695` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-13584` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12125` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-8595` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-19487` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-13437` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11583` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-25311` stop=`completed`
- `mwaskom__seaborn-3407` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11049` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11905` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-17022` stop=`completed`
- `django__django-12908` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15738` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-13779` stop=`completed`
- `django__django-14155` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13757` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-8282` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-13146` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-21055` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-11040` stop=`error`
  - error: 'prompts/feedback.md has no section #readonly_edit_now, #_note_thought_action_loop.readonly_edit_now'
- `sympy__sympy-16988` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12113` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14997` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11742` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15388` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-14092` stop=`error`
  - error: Tests never passed within iteration limit.
- `pylint-dev__pylint-7114` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-16820` stop=`error`
  - error: Tests never passed within iteration limit.
- `pallets__flask-4992` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-16229` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-8721` stop=`completed`
- `django__django-13447` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-18199` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14238` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15819` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-13031` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-7432` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-14396` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12589` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-13496` stop=`completed`
- `pytest-dev__pytest-5495` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11797` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11564` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-22711` stop=`error`
  - error: 'prompts/feedback.md has no section #readonly_edit_now, #_note_action_loop_results.readonly_edit_now'
- `django__django-13964` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-11148` stop=`error`
  - error: Tests never passed within iteration limit.
- `pydata__xarray-3364` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11001` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-24213` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-7686` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-18057` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-15678` stop=`error`
  - error: Tests never passed within iteration limit.
- `pallets__flask-4045` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-14317` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-15790` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-14534` stop=`error`
  - error: Tests never passed within iteration limit.
- `psf__requests-1963` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-13177` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13315` stop=`completed`
- `matplotlib__matplotlib-25433` stop=`completed`
- `sphinx-doc__sphinx-10451` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-7490` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-26011` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11964` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-11870` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-16816` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-25442` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-15609` stop=`completed`
- `django__django-12470` stop=`error`
  - error: Tests never passed within iteration limit.
- `scikit-learn__scikit-learn-25638` stop=`completed`
- `django__django-16595` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12284` stop=`error`
  - error: Tests never passed within iteration limit.
- `pylint-dev__pylint-7993` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-23314` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-5221` stop=`error`
  - error: Tests never passed within iteration limit.
- `astropy__astropy-12907` stop=`completed`
- `scikit-learn__scikit-learn-25570` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-10924` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12184` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-24334` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-22840` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-16041` stop=`error`
  - error: Tests never passed within iteration limit.
- `pylint-dev__pylint-5859` stop=`error`
  - error: Tests never passed within iteration limit.
- `sphinx-doc__sphinx-8801` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-13265` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-13915` stop=`error`
  - error: Tests never passed within iteration limit.
- `pytest-dev__pytest-5103` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-12497` stop=`error`
  - error: Tests never passed within iteration limit.
- `pydata__xarray-4248` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-19007` stop=`error`
  - error: Tests never passed within iteration limit.
- `matplotlib__matplotlib-23913` stop=`completed`
- `django__django-13158` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-21627` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-16792` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-14308` stop=`error`
  - error: 'prompts/feedback.md has no section #readonly_edit_now, #_note_thought_action_loop.readonly_edit_now'
- `sphinx-doc__sphinx-10325` stop=`error`
  - error: Tests never passed within iteration limit.
- `sympy__sympy-14817` stop=`completed`
- `sympy__sympy-17139` stop=`error`
  - error: Tests never passed within iteration limit.
- `django__django-11630` stop=`error`
  - error: Tests never passed within iteration limit.
