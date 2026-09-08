# fold_03_holdout_0008

- 训练任务族：0006, 0007, 0009, 0010
- 验证任务族：0008
- 训练轨迹/决策样本：5 / 1193
- 验证轨迹/决策样本：2 / 434
- rollout 验证任务：2
- 推荐单次划分：否

使用本目录的 `train.jsonl` 与 `validation.jsonl`。通过目标 Qwen tokenizer 的
`apply_chat_template` 渲染 `prompt + completion` 和 `tools`，只对
`completion` token 计算 loss。该 fold 是一场从同一基座重新开始的独立训练实验，
不是一个 epoch。
