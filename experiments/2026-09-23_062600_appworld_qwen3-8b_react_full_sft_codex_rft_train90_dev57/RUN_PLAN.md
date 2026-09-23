# train90 全参数 SFT Dev57 评测执行说明

- 固定最终模型：`/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/artifacts/model`，epoch 5 / optimizer step 2925。
- 对照：`/root/autodl-tmp/workspace-tw/experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57`，仅引用历史官方分数与日志，不重新执行 LoRA。
- 数据集：官方 Dev 57 个任务、19 个场景；顺序与历史评测一致，训练 90 任务与 Dev 无交集。
- 协议：simplified_react_code_agent；qwen3-8b-with-reasoning 配置；temperature=0；seed=100；max_steps=50；max_completion_tokens=3000；vLLM max_model_len=32000；无 reasoning parser。
- 生成配置中的默认 server command 会被运行时覆盖；实际完整模型服务命令见 `logs/run.log`。AppWorld 的 reasoning_content=null 仅规范为空字符串。
- 每完成一题立即使用官方 evaluator 计分并追加 `task_status.jsonl`；全部结束后再运行官方 Dev 聚合评测。
- 模型行为导致的错误、超上下文或预算终止保留在本次轨迹中，不更改上下文/提示词、不挑选成功重试。
- 启动时的临时 socket 路径过长问题发生在任何任务开始之前；原日志保留于 `logs/startup_attempt_01/`。修改为工作区内短 TMPDIR 后重新启动。
- 缓存、报告、日志、任务运行输出均写在 workspace-tw。工作区外的环境与基准源数据只读使用；不创建分支。
- 输出：中文 `REPORT.md`、`summary.json`、`task_comparison.csv`、完整官方评分与轨迹、实际脚本快照和 SHA-256 清单。
- 本次不运行 test_normal，不根据 Dev 结果修改权重或选择 checkpoint。
