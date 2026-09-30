# CFST第6b步：三个分支各训练1轮

**训练及核验已完成。三支均从原Qwen3-8B + train90 LoRA第5轮adapter独立启动；旧第6、7步结果保留。** 本步没有运行检查30题、Dev57或AppWorld轨迹采集。

本轮只改变训练量规则：使用第5步冻结的12/8/20条唯一数据，各自完整训练1轮。每条样本在两张卡合计的参数更新中恰好出现一次，不重复凑8,000监督tokens。学习率等设置与旧第6步相同，原始数据、标签和修复动作不变；只监督教师替代动作，历史仅作输入，修复后的学生续跑不作为训练目标。

| 分支 | 样本次数 | 更新次数 | 监督tokens | 输入tokens（不含padding） | 最后更新loss | 训练包诊断loss | 耗时（秒） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CFST-State-1epoch | 12 | 6 | 1,826 | 101,754 | 0.9085 | 0.3563 | 39.7 |
| CFST-Action-1epoch | 8 | 4 | 1,493 | 99,675 | 0.9039 | 0.4264 | 70.3 |
| CFST-Mixed-1epoch | 20 | 10 | 3,319 | 201,429 | 0.5830 | 0.4028 | 109.2 |

耗时包括更新、训练包诊断和保存，不含模型加载。输入tokens是实际送入模型的历史加答案长度；计算还包含padding、反向传播和梯度检查点重计算，不能用监督tokens或样本数直接代替实际算力。

学习率2e-4、AdamW、weight decay=0、无warmup或调度、全局batch=2、双卡每卡1条、累积1次；LoRA r=8/alpha=16/dropout=0；BF16、SDPA、最大40,960、seed=20260928，训练模板enable_thinking=False。每支建立新的优化器，不从旧CFST分支继续训练。源adapter SHA256为 `c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`。

## 核验结果

282/282项检查通过。核验覆盖：冻结数据哈希、实际样本曝光次数、两卡无重复无遗漏且顺序符合种子、更新步数和token总量、原adapter文件未修改、配置符合计划、模型权重实际变化、三支权重不同，以及重新加载三支adapter后的前向输出有限且彼此不同。训练前记录的旧第6、7步共92个保护文件哈希全部未变。

[完整核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/validation.json) · [实际样本使用审计](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/sample_exposure_audit.json) · [重新加载核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/reload_validation.json) · [结构化结果](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/summary.json)

## 三个独立产物

- [CFST-State-1epoch adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-state/adapter)；[训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-state/REPORT.md)
- [CFST-Action-1epoch adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Action/adapter)；[训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Action/REPORT.md)
- [CFST-Mixed-1epoch adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Mixed/adapter)；[训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Mixed/REPORT.md)

每支目录同时保存唯一训练清单、预期两卡分区、配置、原始日志、逐步loss和权重。执行入口为 `run_step06b.py`，它拒绝覆盖已有训练日志；训练程序与旧第6步逐字相同，变化发生在生成单轮清单和验收规则上。[执行前计划快照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/PLAN_SNAPSHOT.md) 与 `training_plan.json` 保留冻结时状态；完成状态以本报告、`status.json` 和 `summary.json` 为准。

## 现在能说明什么

三个模型按预定一轮训练量完成并可加载。训练loss不能判断任务成功率，也不能凭三个数据包的loss差异证明能力分类合理；第一与最后一步使用不同样本，不能简单比较。诊断loss只反映各自训练包上的拟合，不是检查30题的结果。没有因为loss高低加训或挑选中间权重。

旧版State/Action/Mixed使用54/44/50次样本、27/22/25次更新；本轮为12/8/20次样本、6/4/10次更新。之后若执行第7b步，仍按原评测协议比较这三个新adapter与原epoch5的17/30，以及旧版13/14/14的结果。本步到训练核验结束；当前学生仍保留原epoch5，不宣布任何新分支已带来改善。

[训练loss图](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/training_loss.png) · [PDF图](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/training_loss.pdf)
