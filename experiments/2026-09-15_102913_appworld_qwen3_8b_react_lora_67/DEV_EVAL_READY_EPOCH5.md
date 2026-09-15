# AppWorld Dev 五轮 LoRA 评测入口

最终 adapter：`/root/autodl-tmp/workspace-tw/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/artifacts/continuation/adapter_epoch5`

```bash
cd /root/autodl-tmp/workspace-tw
EVAL_EXPERIMENT="/root/autodl-tmp/workspace-tw/experiments/$(date +%Y-%m-%d_%H%M%S)_appworld_qwen3-8b_react_lora_full_dev"
bash scripts/run_appworld_qwen3_react_lora_full_dev.sh \
  "$EVAL_EXPERIMENT" \
  /root/autodl-tmp/workspace-tw/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/artifacts/continuation/adapter_epoch5
```

该命令使用官方 57 题 Dev split 和 evaluator。本训练任务未自动启动 Dev 评测。
