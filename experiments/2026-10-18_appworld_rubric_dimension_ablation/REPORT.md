# Rubric 完整删除消融运行结果

> **新增联合分析：** [DropR1/DropR2 的共同移除样本、R3/R6 暴露与 evaluator 收益](REPORT_THREE_SEEDS.md#r1-r2-joint-analysis)。两组共同移除359条候选，实际训练步骤约92%相同；R6仍是候选机制，尚未与R3及其他内容变化分离。

> **完整最终分析请看 [三 seed 最终报告](REPORT_THREE_SEEDS.md)**：[R5/R7 的 PASS 正例](REPORT_THREE_SEEDS.md#r5-r7-positive-examples)、[旧 ZeroFail3 与本轮训练预算对比](REPORT_THREE_SEEDS.md#baseline-and-budget)、[evaluator 总表](REPORT_THREE_SEEDS.md#evaluator-overview)、[全部家族](REPORT_THREE_SEEDS.md#evaluator-all-families)及[逐组八类检查得失](REPORT_THREE_SEEDS.md#evaluator-type-details)。下文保留 GPU1 两个 seed 的历史汇总。

更新时间：2026-10-19T19:34:43+08:00（北京时间）。实际训练对应的 DEV57 已完成 14/14；未完成结果不填为零。

八个报告组各 1,358 步、1 epoch、两个 seed，仅按剩余七项 P≥3 且 F=0 选样。DropR7 复用同 seed 新 DropR5，不计独立证据。没有 Random/ZeroFail3 训练项目；DropR5 的候选集合恰好等价于全规则集合。

| 组 | seed | 成功 | TGC | 来源 |
| --- | ---: | ---: | ---: | --- |
| drop_r1 | 20261015 | 10/57 | 17.54% | 独立训练 |
| drop_r2 | 20261015 | 9/57 | 15.79% | 独立训练 |
| drop_r3 | 20261015 | 6/57 | 10.53% | 独立训练 |
| drop_r4 | 20261015 | 5/57 | 8.77% | 独立训练 |
| drop_r5 | 20261015 | 6/57 | 10.53% | 独立训练 |
| drop_r6 | 20261015 | 2/57 | 3.51% | 独立训练 |
| drop_r7 | 20261015 | 6/57 | 10.53% | 复用 DropR5 |
| drop_r8 | 20261015 | 6/57 | 10.53% | 独立训练 |
| drop_r1 | 20261016 | 10/57 | 17.54% | 独立训练 |
| drop_r2 | 20261016 | 10/57 | 17.54% | 独立训练 |
| drop_r3 | 20261016 | 8/57 | 14.04% | 独立训练 |
| drop_r4 | 20261016 | 4/57 | 7.02% | 独立训练 |
| drop_r5 | 20261016 | 7/57 | 12.28% | 独立训练 |
| drop_r6 | 20261016 | 6/57 | 10.53% | 独立训练 |
| drop_r7 | 20261016 | 7/57 | 12.28% | 复用 DropR5 |
| drop_r8 | 20261016 | 7/57 | 12.28% | 独立训练 |

逐题配对见 [comparisons.json](analysis/comparisons.json)，选样分布见 [SELECTION_SUMMARY.json](data/SELECTION_SUMMARY.json)。两个 seed 的区间不完整覆盖训练随机性，无同预算随机对照，不能证明普遍优于随机选样。相同历史动作探测尚未运行，当前报告不声称学习机制已被验证。
