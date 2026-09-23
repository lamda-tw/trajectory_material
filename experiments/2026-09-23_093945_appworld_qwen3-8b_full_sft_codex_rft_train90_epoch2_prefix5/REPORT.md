# train90 全参数SFT两轮训练报告

本次训练已完成 **2轮、1170次更新**，全参数参与更新，共8,190,735,360个参数。以原始Qwen3-8B重新初始化，沿用五轮实验的前1170步学习率路径；warmup88步，计划总跨度2925步。全部实际配置见`config/training_config.json`，精确命令见`command.txt`。

训练耗时约 **69.9分钟**（以训练器计时为准），状态SUCCESS；重载生成检查PASS。每轮导出一份BF16推理模型，保留epoch1和最终epoch2，不存储optimizer重启分片。

| 轮次 | 本次两轮：该轮平均loss | 旧五轮：该轮平均loss |
|---|---|---|
| 1 | 0.589565 | 0.589548 |
| 2 | 0.272481 | 0.274838 |
| 3 | — | 0.129335 |
| 4 | — | 0.053033 |
| 5 | — | 0.016795 |

![loss对比](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch2_prefix5/metrics/loss_comparison.png)

前1170步学习率完全一致，样本长度与监督token序列一致；loss平均绝对差0.026816、最大绝对差0.260682。这是同设置重训，不是旧第2轮权重的逐位恢复。训练重叠诊断loss为0.144292，不代表独立验证集泛化。

两轮与五轮均成功 28/168，总体TGC持平。本次没有观察到任务成功率的提升。完整成功场景为两轮5/56、五轮3/56。

完整评测、控制条件、具体案例和归因边界见[中文评测报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/REPORT.md)。正式test_normal仅评测epoch2；未据test选择检查点。
