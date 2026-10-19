# 三 seed 逐项删除消融汇总

更新时间：2026-10-19T19:34:56+08:00。DEV57 已完成 **21/21** 次独立模型评测；缺失结果不填零。

每组 1,358 步、1 epoch、679 更新；仅按评分选样。GPU1：20261015/20261016；GPU0：20261017。DropR7 复用同 seed DropR5，不计独立训练或重复证据。

| 组 | seed | GPU | 成功 | TGC | 来源 |
| --- | ---: | ---: | ---: | ---: | --- |
| drop_r1 | 20261015 | 1 | 10/57 | 17.54% | [独立训练](evaluation/drop_r1/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r2 | 20261015 | 1 | 9/57 | 15.79% | [独立训练](evaluation/drop_r2/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r3 | 20261015 | 1 | 6/57 | 10.53% | [独立训练](evaluation/drop_r3/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r4 | 20261015 | 1 | 5/57 | 8.77% | [独立训练](evaluation/drop_r4/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r5 | 20261015 | 1 | 6/57 | 10.53% | [独立训练](evaluation/drop_r5/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r6 | 20261015 | 1 | 2/57 | 3.51% | [独立训练](evaluation/drop_r6/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r7 | 20261015 | 1 | 6/57 | 10.53% | [复用 DropR5](evaluation/drop_r5/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r8 | 20261015 | 1 | 6/57 | 10.53% | [独立训练](evaluation/drop_r8/seed_20261015/epoch_01/SUMMARY.json) |
| drop_r1 | 20261016 | 1 | 10/57 | 17.54% | [独立训练](evaluation/drop_r1/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r2 | 20261016 | 1 | 10/57 | 17.54% | [独立训练](evaluation/drop_r2/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r3 | 20261016 | 1 | 8/57 | 14.04% | [独立训练](evaluation/drop_r3/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r4 | 20261016 | 1 | 4/57 | 7.02% | [独立训练](evaluation/drop_r4/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r5 | 20261016 | 1 | 7/57 | 12.28% | [独立训练](evaluation/drop_r5/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r6 | 20261016 | 1 | 6/57 | 10.53% | [独立训练](evaluation/drop_r6/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r7 | 20261016 | 1 | 7/57 | 12.28% | [复用 DropR5](evaluation/drop_r5/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r8 | 20261016 | 1 | 7/57 | 12.28% | [独立训练](evaluation/drop_r8/seed_20261016/epoch_01/SUMMARY.json) |
| drop_r1 | 20261017 | 0 | 16/57 | 28.07% | [独立训练](gpu0_seed_20261017/evaluation/drop_r1/seed_20261017/epoch_01/SUMMARY.json) |
| drop_r2 | 20261017 | 0 | 10/57 | 17.54% | [独立训练](gpu0_seed_20261017/evaluation/drop_r2/seed_20261017/epoch_01/SUMMARY.json) |
| drop_r3 | 20261017 | 0 | 4/57 | 7.02% | [独立训练](gpu0_seed_20261017/evaluation/drop_r3/seed_20261017/epoch_01/SUMMARY.json) |
| drop_r4 | 20261017 | 0 | 9/57 | 15.79% | [独立训练](gpu0_seed_20261017/evaluation/drop_r4/seed_20261017/epoch_01/SUMMARY.json) |
| drop_r5 | 20261017 | 0 | 2/57 | 3.51% | [独立训练](gpu0_seed_20261017/evaluation/drop_r5/seed_20261017/epoch_01/SUMMARY.json) |
| drop_r6 | 20261017 | 0 | 9/57 | 15.79% | [独立训练](gpu0_seed_20261017/evaluation/drop_r6/seed_20261017/epoch_01/SUMMARY.json) |
| drop_r7 | 20261017 | 0 | 2/57 | 3.51% | [复用 DropR5](gpu0_seed_20261017/evaluation/drop_r5/seed_20261017/epoch_01/SUMMARY.json) |
| drop_r8 | 20261017 | 0 | 7/57 | 12.28% | [独立训练](gpu0_seed_20261017/evaluation/drop_r8/seed_20261017/epoch_01/SUMMARY.json) |

| 组 | 已完成 seed | 平均 TGC | 各 seed 成功数 |
| --- | ---: | ---: | --- |
| DropR1 | 3/3 | 21.05% | 20261015: 10/57；20261016: 10/57；20261017: 16/57 |
| DropR2 | 3/3 | 16.96% | 20261015: 9/57；20261016: 10/57；20261017: 10/57 |
| DropR3 | 3/3 | 10.53% | 20261015: 6/57；20261016: 8/57；20261017: 4/57 |
| DropR4 | 3/3 | 10.53% | 20261015: 5/57；20261016: 4/57；20261017: 9/57 |
| DropR5 | 3/3 | 8.77% | 20261015: 6/57；20261016: 7/57；20261017: 2/57 |
| DropR6 | 3/3 | 9.94% | 20261015: 2/57；20261016: 6/57；20261017: 9/57 |
| DropR7 | 3/3 | 8.77% | 20261015: 6/57；20261016: 7/57；20261017: 2/57 |
| DropR8 | 3/3 | 11.70% | 20261015: 6/57；20261016: 7/57；20261017: 7/57 |

主比较是同 seed 的 DropRi 对 DropR5，仅使用两侧均完成的配对；逐题差异、家族 bootstrap 描述区间见 [comparisons.json](analysis_three_seeds/comparisons.json)。完成 seed 数不同的临时均值不能直接排名。三个 seed 仍不足以完整刻画训练随机性；seed 与物理卡没有交叉实验，卡间差异未单独估计。

没有同预算 Random，不据此声称优于随机选样。同状态动作诊断尚未运行，当前报告不声称学习机制已经验证。原 REPORT.md 是 GPU1 两轮分队列报告，此文件才是全三轮汇总。
