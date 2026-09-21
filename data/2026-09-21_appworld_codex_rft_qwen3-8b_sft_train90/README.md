# AppWorld Codex LOOP-style RFT → Qwen3-8B SFT（train90）

本数据集把 90 条官方 evaluator 成功的 Codex RFT 轨迹转换成
1170 条决策级 completion-only SFT 样本。`train.jsonl` 可直接由本仓库
`scripts/minimal_sft_train.py` / `scripts/continue_appworld_react_lora.py` 读取。

## 核心文件

- `train.jsonl`：全部 1170 个下一步 assistant 决策；训练主文件。
- `full_trajectories.jsonl`：90 条完整对话，仅用于审计。
- `tasks/<task_id>.json`：逐题决策样本。
- `difficulty_summary.json`：AppWorld 难度后验统计；不进入模型输入。
- `manifest.json`：来源、哈希、转换策略和计数。
- `validation.json`：运行 Qwen tokenizer 校验脚本后生成。

## 与 ground-truth 教师轨迹的差异

这些动作由 Codex 在真实环境 observation 上闭环产生，不使用 solution、隐藏 evaluator
断言或 ground-truth API 序列。它们包含真实文档探索、状态检查、冗余动作，以及
9 条成功轨迹中的执行错误恢复。模型消息只使用采样时 Codex 实际
看到的脱敏 `policy_observation`；raw observation 不进入本数据集。
每轮 observation 还复现采样时的 24,000 字符前后截断，因此不会误纳入 Codex 未看到的内容。

但这不是“保证提升”的数据：90 条成功轨迹只有一个任务曾触发 RFT 拒绝重采，策略风格
仍主要来自单一强教师 Codex。建议先做受控 LoRA，对比相同基座、相同超参数的旧数据、
本数据和混合数据，并以 held-out AppWorld Dev 的官方闭环指标为准。

## 训练契约

每行使用 Qwen chat template，`enable_thinking=False`；prompt 与 padding label 设为 -100，
仅单条 assistant completion 参与 loss。不要把 `full_trajectories.jsonl` 当作整轨迹 target。
推荐 `max_length=40960`，即 Qwen3-8B 的原生上下文上限。
