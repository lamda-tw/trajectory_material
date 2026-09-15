# AppWorld Dev 评测准备

最终全参数 SFT 模型：

`/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/artifacts/model`

建议创建独立 Dev 实验目录后执行：

```bash
cd /root/autodl-tmp/workspace-tw
EVAL_DIR=/root/autodl-tmp/workspace-tw/experiments/$(date +%Y-%m-%d_%H%M%S)_appworld_qwen3-8b_react_full_sft_full_dev
bash scripts/run_appworld_qwen3_react_full_sft_full_dev.sh "$EVAL_DIR" "/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/artifacts/model"
```

该命令会运行 AppWorld Dev 官方 evaluator；不要把本训练实验中的诊断 loss 当作 Dev 成绩。
