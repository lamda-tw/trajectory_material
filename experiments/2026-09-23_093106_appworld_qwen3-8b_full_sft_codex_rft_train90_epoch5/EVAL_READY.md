# 模型与评测入口

最终模型：`/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/artifacts/model`。完整续训检查点已按要求清理；保留的 BF16 模型可用于推理和评测。

模型重载与权重 SHA-256 核验通过。Dev 57 题评测已完成：**12/57 成功，TGC 21.1，SGC 0.0**；同数据五轮 LoRA 为 23/57，TGC 40.4，SGC 21.1。

- [Dev 中文报告](../2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/REPORT.md)
- [逐题 LoRA 对照](../2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/task_comparison.csv)
- [官方分数与审计](../2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/summary.json)
- [训练报告](REPORT.md)

本模型尚未运行 test_normal。Dev 评测固定最终 epoch 5 权重，未选择中间 checkpoint。
