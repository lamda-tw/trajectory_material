# 模型与评测入口

最终模型：`/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/artifacts/model`。完整续训检查点已按要求清理；保留的 BF16 模型可用于推理和评测。

模型重载与权重 SHA-256 核验通过。Dev 57 题评测已完成：**12/57 成功，TGC 21.1，SGC 0.0**；同数据五轮 LoRA 为 23/57，TGC 40.4，SGC 21.1。

- [Dev 中文报告](../2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/REPORT.md)
- [逐题 LoRA 对照](../2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/task_comparison.csv)
- [官方分数与审计](../2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/summary.json)
- [训练报告](REPORT.md)

test_normal 168题现已完成：**28/168 成功，TGC 16.7，SGC 5.4**；同协议LoRA为51/168、30.4、16.1。共同成功18题，新增成功10题，退化33题。两次评测都固定最终 epoch 5 权重，未选择中间checkpoint。

- [test_normal详细中文报告](../2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/REPORT.md)
- [test_normal逐题对照](../2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/task_comparison.csv)
- [性能与训练loss图](../2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/metrics/)
- [test_normal最终核验](../2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/metrics/final_validation.json)

训练loss更低没有带来更高的Dev/Test任务完成率；是否5轮过多仍需同一训练轨迹的早期checkpoint与Dev曲线验证。
