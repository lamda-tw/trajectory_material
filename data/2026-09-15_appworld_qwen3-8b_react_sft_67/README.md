# AppWorld Qwen3-8B ReAct SFT data (67 verified train tasks)

This dataset converts 67 official-evaluator-successful and clean-replay-successful AppWorld
trajectories into the completion-only chat format consumed by
`scripts/minimal_sft_train.py` and by standard Hugging Face/TRL PEFT trainers.

## Files

- `train.jsonl`: all 640 assistant decisions from all 67 tasks. Each row has
  `id`, `prompt`, one-message `completion`, `tools: null`, and metadata.
- `tasks/<task_id>.json`: 67 per-task JSON arrays containing the same direct SFT records.
- `full_trajectories.jsonl`: one complete AppWorld chat trajectory per task, including real
  observations after every action.
- `splits/task_holdout_60_7/`: deterministic task-disjoint 60-task train / 7-task validation
  monitor split. This is useful for pipeline checks; official Dev remains the final evaluation.
- `manifest.json`: input provenance, hashes, counts, and conversion policy.
- `validation.json`: structural, tokenizer, prefix, and leak-surface validation results.

## Training contract

Render each row with the Qwen3 chat template using `enable_thinking=False`. Mask every prompt token
with label `-100` and apply loss only to the single assistant completion. No OpenAI function-tool
schema is used: AppWorld expects visible rationale followed by exactly one fenced Python code block.

For a task-disjoint monitored run with the existing trainer:

```bash
/root/autodl-tmp/workspace-tw/.conda-training/bin/python scripts/minimal_sft_train.py \
  --train-json /root/autodl-tmp/workspace-tw/data/2026-09-15_appworld_qwen3-8b_react_sft_67/splits/task_holdout_60_7/train.jsonl \
  --validation-json /root/autodl-tmp/workspace-tw/data/2026-09-15_appworld_qwen3-8b_react_sft_67/splits/task_holdout_60_7/validation.jsonl \
  --model /root/autodl-tmp/models/Qwen3-8B \
  --max-length 32768 \
  --output-dir experiments/<timestamp>_appworld_qwen3_8b_react_lora
```

All 640 samples fit within 32,768 tokens with the local Qwen3 tokenizer. The trainer's default
`--max-length 4096` would truncate 331 samples, so use 32,768 for this dataset unless a later
experiment intentionally studies context truncation.

`train.jsonl` intentionally contains all 67 tasks for a final all-data fit before the held-out
AppWorld Dev evaluation. The conversion does not start Qwen, vLLM, SFT, or LoRA training.
