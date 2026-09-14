# Qwen3-8B + mini-SWE-agent SWE-bench Verified-50 baseline v2

## Outcome

The patch-generation run completed all **50/50** frozen tasks. It produced **11 non-empty formal patches**; **10** of them passed `git apply --check` against their exact base commit. This server did not run the official SWE-bench evaluator, so this experiment has no resolved/pass score.

There were 12 `Submitted` exits, including 1 submission(s) whose formal patch was empty; 29 tasks reached the fixed 60-call limit and 9 reached the fixed 40,960-token context boundary. Empty predictions were retained and no poor-quality model result was retried.

## Frozen holdout

Source: `/root/autodl-tmp/data/swebench/tasks/verified/78f471bf655a3137b2e8a75af1501690ec009ec3/test.jsonl`  
Source SHA-256: `a26fafa3f94d5c0b64318998cb6ec80240ba242ace3904c31938bd3346d4ee5c`  
Selection seed: `20260914`  
Selection: one task per repository followed by proportional largest-remainder allocation; within each repository and for final ordering, tasks were sorted by `sha256(seed + "\0" + instance_id)`.

| Repository | Tasks |
| --- | ---: |
| `astropy/astropy` | 3 |
| `django/django` | 18 |
| `matplotlib/matplotlib` | 4 |
| `mwaskom/seaborn` | 1 |
| `pallets/flask` | 1 |
| `psf/requests` | 2 |
| `pydata/xarray` | 3 |
| `pylint-dev/pylint` | 2 |
| `pytest-dev/pytest` | 2 |
| `scikit-learn/scikit-learn` | 3 |
| `sphinx-doc/sphinx` | 4 |
| `sympy/sympy` | 7 |

These 50 instances are a permanent evaluation holdout. They, their gold/test patches, official tests, and derived answers must be excluded from all later SFT, validation, distillation, and trajectory data.

## Reproducible configuration

- Model checkpoint: `/root/autodl-tmp/models/Qwen3-8B` (`openai/qwen3-8b`)
- mini-SWE-agent: 2.4.6 at source commit `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`
- vLLM: 0.10.2; bfloat16; tensor parallel size 1; max model length 40,960
- Sampling: temperature 0.6, top_p 0.95, request seed 20260914, maximum 2,048 output tokens, thinking disabled
- Agent: text-based shell actions, 60-call limit, 180-second shell-command timeout, one formal attempt per task
- Repositories: sanitized source exports at exact base commits; later repository history was not exposed to the agent
- Network: model shell environment used invalid outbound proxies and the prompt prohibited clone, fetch, download, and network access

## Parallel execution

Two identical vLLM replicas were used: GPU 0 on port 18080 and GPU 1 on port 18081. Each replica used `max_num_seqs=2`; worker 0 -> GPU 0, worker 1 -> GPU 1. Assignment was fixed as `worker_id = task_index % 2`.

The 2-request concurrency smoke test passed. The experiment completed in 3 vLLM service segment(s). No formal model result was retried.

- First formal start: `2026-09-14T07:04:19.998895+00:00`
- Final finish: `2026-09-14T08:16:13.018815+00:00`
- Active runner time across 3 segment(s): 51 min 17.7 s
- End-to-end time including diagnosis/resume pause: 1 h 11 min 53.0 s
- Sum of per-task elapsed times: 1 h 25 min 25.4 s
- Work-equivalent concurrency ratio (`sum(task time) / active runner time`): 1.67×
- Formal retry count: 0

Exact peak `nvidia-smi` process memory was not sampled continuously, so no peak value is fabricated. Each vLLM engine used a configured 0.45 GPU-memory utilization; it reported 42.74 GiB on GPU 0 and 42.74 GiB on GPU 1. Full-context KV capacities were 4.74× and 4.74× respectively.

## Aggregate results

| Measure | Count |
| --- | ---: |
| Completed task records | 50 |
| Submitted exits | 12 |
| LimitsExceeded | 29 |
| ContextWindowExceeded | 9 |
| Empty formal patches | 39 |
| Non-empty formal patches | 11 |
| Non-empty patches passing apply-check | 10 |
| Worktrees deleted by model action | 1 |
| Unresolved infrastructure failures | 0 |
| Formal model retries | 0 |

`git apply --check` validates patch syntax and applicability only. It is not a correctness test.

## Per-task results

| # | Instance | Worker/GPU | Seconds | Exit | Formal bytes | Apply-check |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 0 | `django__django-12155` | 0/0 | 7.829 | `Submitted` | 660 | pass |
| 1 | `scikit-learn__scikit-learn-13142` | 1/1 | 75.122 | `LimitsExceeded` | 0 | not run (empty) |
| 2 | `scikit-learn__scikit-learn-11310` | 0/0 | 17.374 | `Submitted` | 492 | pass |
| 3 | `django__django-15973` | 1/1 | 82.048 | `LimitsExceeded` | 0 | not run (empty) |
| 4 | `pydata__xarray-4695` | 0/0 | 195.559 | `LimitsExceeded` | 0 | not run (empty) |
| 5 | `scikit-learn__scikit-learn-25931` | 1/1 | 77.348 | `LimitsExceeded` | 0 | not run (empty) |
| 6 | `pydata__xarray-6992` | 0/0 | 25.935 | `Submitted` | 458 | pass |
| 7 | `matplotlib__matplotlib-22871` | 1/1 | 68.837 | `ContextWindowExceeded` | 0 | not run (empty) |
| 8 | `matplotlib__matplotlib-24026` | 0/0 | 128.059 | `Submitted` | 496 | pass |
| 9 | `astropy__astropy-14182` | 1/1 | 606.519 | `ContextWindowExceeded` | 0 | not run (empty) |
| 10 | `django__django-14855` | 0/0 | 24.880 | `Submitted` | 0 | not run (empty) |
| 11 | `sympy__sympy-21596` | 1/1 | 99.206 | `LimitsExceeded` | 0 | not run (empty) |
| 12 | `matplotlib__matplotlib-24970` | 0/0 | 82.977 | `LimitsExceeded` | 0 | not run (empty) |
| 13 | `matplotlib__matplotlib-26113` | 1/1 | 93.436 | `LimitsExceeded` | 0 | not run (empty) |
| 14 | `sphinx-doc__sphinx-9320` | 0/0 | 259.929 | `ContextWindowExceeded` | 0 | not run (empty) |
| 15 | `sympy__sympy-17139` | 1/1 | 158.951 | `LimitsExceeded` | 0 | not run (empty) |
| 16 | `django__django-11087` | 0/0 | 67.599 | `LimitsExceeded` | 0 | not run (empty) |
| 17 | `pydata__xarray-2905` | 1/1 | 116.598 | `LimitsExceeded` | 0 | not run (empty) |
| 18 | `django__django-15380` | 0/0 | 109.505 | `LimitsExceeded` | 0 | not run (empty) |
| 19 | `astropy__astropy-7166` | 1/1 | 210.890 | `ContextWindowExceeded` | 0 | not run (empty) |
| 20 | `django__django-12663` | 0/0 | 117.419 | `ContextWindowExceeded` | 0 | not run (empty) |
| 21 | `sphinx-doc__sphinx-9367` | 1/1 | 15.309 | `Submitted` | 482 | pass |
| 22 | `django__django-16595` | 0/0 | 67.072 | `LimitsExceeded` | 0 | not run (empty) |
| 23 | `sphinx-doc__sphinx-8459` | 1/1 | 82.499 | `LimitsExceeded` | 0 | not run (empty) |
| 24 | `sympy__sympy-23534` | 0/0 | 125.134 | `LimitsExceeded` | 0 | not run (empty) |
| 25 | `sympy__sympy-19346` | 1/1 | 20.834 | `Submitted` | 563 | pass |
| 26 | `django__django-15732` | 0/0 | 80.728 | `ContextWindowExceeded` | 0 | not run (empty) |
| 27 | `sympy__sympy-16597` | 1/1 | 75.218 | `LimitsExceeded` | 0 | not run (empty) |
| 28 | `django__django-15987` | 0/0 | 75.573 | `LimitsExceeded` | 0 | not run (empty) |
| 29 | `django__django-12741` | 1/1 | 12.993 | `Submitted` | 2391 | pass |
| 30 | `django__django-11490` | 0/0 | 68.544 | `LimitsExceeded` | 0 | not run (empty) |
| 31 | `django__django-13195` | 1/1 | 7.722 | `Submitted` | 613 | pass |
| 32 | `sympy__sympy-14248` | 0/0 | 84.225 | `LimitsExceeded` | 0 | not run (empty) |
| 33 | `django__django-11603` | 1/1 | 171.782 | `LimitsExceeded` | 0 | not run (empty) |
| 34 | `django__django-13023` | 0/0 | 124.560 | `LimitsExceeded` | 0 | not run (empty) |
| 35 | `django__django-11133` | 1/1 | 63.408 | `LimitsExceeded` | 0 | not run (empty) |
| 36 | `django__django-14534` | 0/0 | 82.286 | `LimitsExceeded` | 0 | not run (empty) |
| 37 | `django__django-16255` | 1/1 | 144.256 | `LimitsExceeded` | 0 | not run (empty) |
| 38 | `django__django-14311` | 0/0 | 157.108 | `Submitted` | 181 | fail |
| 39 | `sympy__sympy-18189` | 1/1 | 62.702 | `ContextWindowExceeded` | 0 | not run (empty) |
| 40 | `pylint-dev__pylint-7080` | 0/0 | 75.081 | `ContextWindowExceeded` | 0 | not run (empty) |
| 41 | `sphinx-doc__sphinx-9461` | 1/1 | 97.205 | `LimitsExceeded` | 0 | not run (empty) |
| 42 | `astropy__astropy-14539` | 0/0 | 231.967 | `ContextWindowExceeded` | 0 | not run (empty) |
| 43 | `psf__requests-1921` | 1/1 | 84.608 | `LimitsExceeded` | 0 | not run (empty) |
| 44 | `pytest-dev__pytest-7432` | 0/0 | 86.217 | `LimitsExceeded` | 0 | not run (empty) |
| 45 | `pytest-dev__pytest-10356` | 1/1 | 73.707 | `LimitsExceeded` | 0 | not run (empty) |
| 46 | `pylint-dev__pylint-6386` | 0/0 | 38.985 | `Submitted` | 1927 | pass |
| 47 | `psf__requests-6028` | 1/1 | 98.467 | `LimitsExceeded` | 0 | not run (empty) |
| 48 | `mwaskom__seaborn-3187` | 0/0 | 160.158 | `LimitsExceeded` | 0 | not run (empty) |
| 49 | `pallets__flask-5014` | 1/1 | 31.056 | `Submitted` | 569 | pass |

## Integrity and storage

- Final validation: `passed`
- Shared SWE-bench snapshot unchanged: `True`
- `/root/autodl-tmp/envs` top-level entries unchanged: `True`
- Completed task worktrees and task environments were removed after artifacts were verified.
- Experiment directory size while building this report: 24.31 MiB
- Important retained files are covered by `artifacts.sha256`.

## External official evaluation

Transfer `predictions.jsonl` unchanged to a machine with the official SWE-bench evaluation environment and run it against the matching SWE-bench Verified split. Preserve this experiment's model identifier and frozen instance list. Record the official harness version, image versions, command, and per-instance grading output beside the copied predictions. Do not merge scorer output back into this generation baseline in a way that obscures provenance.

This 50-task fixed holdout is intended for a minimal before/after SFT comparison. It must not be presented as the model's score on the complete 500-task SWE-bench Verified benchmark.
