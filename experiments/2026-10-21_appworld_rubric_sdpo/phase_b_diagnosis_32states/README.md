# 32 个固定状态诊断

**诊断已完成：** [完整报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/REPORT.md)；[完整性核验](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_diagnosis_32states/verification.json)。32 个状态、144 个分支、565 个动作，训练更新为 0。

沿用 `2026-10-21_appworld_rubric_sdpo` 总实验目录，在本子目录独立记录 B 阶段失败后的机制诊断。

- 授权范围：GPU1 推理、AppWorld 回放、旧 checkpoint 的概率/loss 复算。新训练更新为 0，新增 Codex 请求为 0。
- [实验协议](PROTOCOL.md)：抽样、条件、短续跑与评估口径。
- `config/manifest.json`：固定的 32 个 train 状态；不使用 dev57 抽样。
- `states/`：原始输入、旧回答、已有反馈与来源校验。
- `replay/`：精确状态恢复核验。
- `runs/`：初始模型、最终 EMA 教师、最终学生的 C0/C2 候选和执行记录。
- `probabilities/`：原错误前缀上的概率与梯度信号、历史 B loss 复算。
- `analysis/`：结构化行为统计和案例复核。
- `STATUS.json`、`generation.log`、`distribution.log`：运行状态与日志。

本目录包含实验原始任务数据和执行记录。报告只摘录必要的脱敏案例；不将其作为新的训练数据自动使用。
