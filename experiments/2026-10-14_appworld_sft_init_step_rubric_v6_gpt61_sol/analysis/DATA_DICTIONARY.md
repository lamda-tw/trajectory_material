# 评分文件说明

正式全量文件由评分完成后的 `scripts/analyze_results.py` 生成；带 `pilot_` 前缀的文件仅含最初 8 条试评，不能误当作全量结果。

- `step_labels.csv` / `step_labels.jsonl`：每个原始步骤一行，预计 9,886 行。`trajectory_id` 使用 `sft-init:` 前缀区分策略来源；`id` 对应源文件名（不含扩展名）；`task_id` 是 AppWorld 任务标识；`step_id` 是原始一基步骤编号。`labels` 的八个字符依次为 R1—R8；各维度也展开为单独列。`reason` 是裁判的原始简短英文依据。纯 P/N 步骤的依据为空。
- `scored_trajectories.jsonl`：预计 540 行，每行保留一条完整轨迹的原始有效 JSON 评分对象，含 `trajectory_id`、`rubric_version`、`steps`。每个步骤为 `[step_id, eight_character_labels, reason]`。
- `trajectory_metrics.csv`：每轨迹的分布统计以及研究者使用的官方成功标记。官方标记未传入裁判。
- `outcome_association.csv`：按官方成败分组的标签数量以及 P/F 子集上的描述性 phi 相关。排除 U/N 不表示它们是负例；步骤相关性使这些数值不能解释为独立样本推断或准确率。
- `mechanical_review_flags.json`：保守程序规则产生的疑点，需结合原始证据复核；不自动修改标签。为空仅说明没有触发这些规则。
- `validation.json`：全量结构、哈希、配置、原始步骤顺序、唯一性和首个有效响应策略的验收。
- `summary.json` / `attempts.json`：标签分布、调用使用量以及全部有效/无效尝试。使用量按服务报告字段记录；未报告的失败消耗无法推定为零。

标签：P 表示适用且证据支持满足；F 表示适用且证据明确违反；U 表示适用但证据不足；N 表示不适用。R1 执行有效性；R2 证据与覆盖；R3 状态与数据忠实度；R4 决策逻辑与计算；R5 动作与真实效果；R6 反馈与恢复；R7 终止与交付；R8 授权与交互协议。精确定义以冻结 prompt 为准。

不合成总分，不给维度预设权重，不把 N 当作 P，不把 U 当作 F。R7=P 可能表示诚实报告失败，并不保证任务成功。语义复核意见单独保存，汇总文件始终保留首次有效裁判输出。
