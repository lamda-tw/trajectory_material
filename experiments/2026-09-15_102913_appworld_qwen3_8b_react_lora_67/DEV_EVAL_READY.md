# AppWorld Dev evaluation readiness

The trained LoRA adapter is:

`/root/autodl-tmp/workspace-tw/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/artifacts/adapter`

It has already been reloaded with PEFT and produced one AppWorld-compatible ReAct response with
exactly one non-empty fenced Python code block.

To run the complete held-out AppWorld Dev evaluation later:

```bash
cd /root/autodl-tmp/workspace-tw
EVAL_EXPERIMENT="/root/autodl-tmp/workspace-tw/experiments/$(date +%Y-%m-%d_%H%M%S)_appworld_qwen3-8b_react_lora_full_dev"
bash scripts/run_appworld_qwen3_react_lora_full_dev.sh \
  "$EVAL_EXPERIMENT" \
  /root/autodl-tmp/workspace-tw/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/artifacts/adapter
```

The runner uses the unchanged local `/root/autodl-tmp/models/Qwen3-8B` base, serves this adapter
through vLLM with `--enable-lora`, preserves the existing one-shot
`simplified_react_code_agent` protocol, runs the official 57-task Dev split, and invokes the
official evaluator. It isolates all runtime state beneath the new evaluation experiment directory.

This document only records the ready command. The full Dev evaluation was not started by the
training run.
