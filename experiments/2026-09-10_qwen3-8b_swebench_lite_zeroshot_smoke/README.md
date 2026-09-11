# Qwen3-8B × SWE-bench Lite zero-shot smoke experiment

This experiment runs three fixed `SWE-bench_Lite/dev` tasks with the local
`Qwen3-8B` checkpoint. It is deliberately small and is intended to make the
end-to-end data flow inspectable.

The model receives only the issue statement and source files selected from the
repository at `base_commit`. It does not receive demonstrations, the reference
patch, `test_patch`, `FAIL_TO_PASS`, or `PASS_TO_PASS`.

The inference mode is a minimal single-turn baseline, not a full tool-using
agent. A deterministic retriever ranks repository files using filenames and
identifiers found in the issue, then asks the model for one unified diff.

## Layout

- `config.json`: fixed model, dataset revision, task IDs, and decoding settings
- `data/selected_tasks.jsonl`: exact public task inputs used
- `repos/`: one source clone per upstream repository
- `worktrees/`: independent checkout and model edits for each task
- `prompts/`: exact rendered prompts and selected-file manifests
- `outputs/`: raw model generations
- `patches/`: parsed model patches
- `predictions.jsonl`: SWE-bench prediction records
- `checks/`: post-inference, non-authoritative local test results
- `logs/`: preparation, inference, and test logs
- `REPORT.md`: final interpretation and limitations

## Reproduction

From the workspace root:

```bash
.conda-training/bin/python experiments/2026-09-10_qwen3-8b_swebench_lite_zeroshot_smoke/scripts/prepare_worktrees.py

HF_HOME=experiments/2026-09-10_qwen3-8b_swebench_lite_zeroshot_smoke/cache/huggingface \
XDG_CACHE_HOME=experiments/2026-09-10_qwen3-8b_swebench_lite_zeroshot_smoke/cache/xdg \
CUDA_VISIBLE_DEVICES=0 \
.conda-training/bin/python \
  experiments/2026-09-10_qwen3-8b_swebench_lite_zeroshot_smoke/scripts/run_inference.py

PYTHONPATH=/root/autodl-tmp/data/swebench/.tools/python \
.conda-training/bin/python \
  experiments/2026-09-10_qwen3-8b_swebench_lite_zeroshot_smoke/scripts/run_checks.py
```

`run_checks.py` reads hidden grader fields only after inference. Its results are
not an official SWE-bench score because this host does not currently provide
the official per-instance Docker runtime.
