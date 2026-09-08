# fold_02_holdout_0007

- 训练任务族：0006, 0008, 0009, 0010
- 验证任务族：0007
- 训练轨迹/决策样本：6 / 1497
- 验证轨迹/决策样本：1 / 130
- rollout 验证任务：1
- 推荐单次划分：否

使用本目录的 `train.jsonl` 与 `validation.jsonl`。通过目标 Qwen tokenizer 的
`apply_chat_template` 渲染 `prompt + completion` 和 `tools`，只对
`completion` token 计算 loss。该 fold 是一场从同一基座重新开始的独立训练实验，
不是一个 epoch。
