# 第2步：固定划分与失败审查

**已完成离线分析；修复验证未开始，成功修复样本为0。** 复用第一步已有90题轨迹，没有重跑Qwen3-8B、调用教师、重放环境或训练模型。

## 实际完成了什么

种子固定为20260928，按难度1/2/3分层、整任务族划分。来源60题来自20族，检查30题来自10族，两侧任务及任务族均不重叠。难度分布分别为24/24/12与12/12/6。

| 分组 | 成功 | 失败 | 其中上下文超限 | 未超限失败 |
| --- | --- | --- | --- | --- |
| 修复来源60题 | 29 | 31 | 8 | 23 |
| 效果检查30题 | 17 | 13 | 1 | 12 |

只审查来源侧10个未超限失败，来自10个不同任务族，难度1/2/3各1/6/3例。每例都记录任务要求、官方失败条件、疑似替换动作、日志证据、暂定类别、修复方向、输入定位和剩余预算。

这30道检查题也参加过旧LoRA的SFT；它们只是不提供本轮新增修复答案，不能称为模型从未见过的测试集。检查侧本次只汇总已有成绩，没有审查其轨迹来挑修复步骤。

## 首批候选与备选

| 顺序 | 题号 | 替换动作 | 具体问题 |
| --- | --- | --- | --- |
| 首选1 | ccb4494_2 | 第6步 | 歌曲位置与自己比较，条件恒真，将未播放歌曲也选入点赞集合 |
| 首选2 | 302c169_2 | 第11步 | 要求停用其他闹钟，学生却删除了它们 |
| 首选3 | 60d0b5b_1 | 第14步 | 修正退款接口参数名后，仍沿用未精确筛选收款人的错误金额 |
| 备选1 | 34d9492_2 | 第13步 | 整理照片只检查月份，漏掉文件年份 |
| 备选2 | 22cc237_3 | 第18步 | 应向欠款人发付款请求，却向他们转账 |

5例均有可尝试的局部修复方向，另外5例暂列可能需要多步修复，保留原审查记录。10例暂定主标签为状态7、恢复2、参数1；首选没有恢复类，不强行凑齐三类。这些标签是工作判断，不是已证明的因果解释。

## 文件怎么读

- 先看 [10例审查报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/failure_review.md)：逐题解释和原始日志链接。
- [候选索引](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/repair_candidates.jsonl)：首选与备选顺序、原始输入位置、预算和未验证状态。
- [冻结划分](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/task_split.json)、[来源60题](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/source_task_ids.txt)、[检查30题](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/check_task_ids.txt)：包含种子、分层规则、输入校验值。
- [来源侧清单](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/source_task_inventory.csv)、[审查顺序](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/review_queue.csv)：31个失败的完整队列，未审查案例仍在队列里。
- [结构化案例卡](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/review_annotations.jsonl)、[结果统计](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/summary.json)、[本步执行范围](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/manifest.json)。
- [一致性核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/validation.json)、[产物校验值](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/artifact_sha256.json)：划分、评分计数、引用和原始证据完整性。

`prepare_step02.py`记录划分算法并拒绝覆盖已有划分；`inspect_saved_trajectories.py`只读原始轨迹；`write_review.py`保存人工审查判断并生成报告；`validate_step02.py`只做数据一致性核验。原始轨迹继续保留在第一步目录。

## 下一步及边界

第3步才会做真实验证：从干净环境重放候选动作前的历史，替换一个动作，让原Qwen3-8B + train90 LoRA第5轮adapter续跑，并按官方评分判断成功。先按上表顺序尝试；若不足3条成功修复，再从来源侧剩余审查队列找候选。**必须得到3条实际通过官方评分的修复，才能扩大采集或训练。**

目前所有候选都是未验证，输入能放进原窗口、还有动作预算，并不能证明续跑成功。教师未来只能看到候选动作之前的原始历史，不能将这份审查报告、官方失败条件或之后的轨迹拼进教师输入。

[当前实验待办](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md)
