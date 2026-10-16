# SFT 初始模型 AppWorld 540 条轨迹评分：已完成

英文 v6 format prompt；GPT-6.1 sol / high；540 条、9,886 步、79,088 个标签。覆盖与来源验收通过；评分阶段耗时 151.21 分钟。未训练或改动源模型。

- [完整报告](REPORT.md)
- [逐步标签 CSV](analysis/step_labels.csv)
- [逐步标签 JSONL](analysis/step_labels.jsonl)
- [完整逐轨迹评分 JSONL](analysis/scored_trajectories.jsonl)
- [评分清单和哈希](score_manifest.json)
- [文件与标签说明](analysis/DATA_DICTIONARY.md)
- [结构验收](analysis/validation.json) · [语义复核](review/semantic_review.json)

数据唯一来源为 `2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories`。本目录独立保存输入、prompt、schema、配置、来源清单、原始响应和重试日志。不是原始基座模型那批轨迹。语义问题另记，原始裁判结果不静默修改。
