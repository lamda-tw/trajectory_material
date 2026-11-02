# 同 seed 纯 ZeroFail3 SFT：恒定学习率与余弦衰减对照

更新时间：2026-10-28T09:44:16.602156+08:00。三轮训练和三次 dev57 评估全部完成。
已提交 54/54 批，优化器更新 54 次。GPU1，无时间上限，三轮完成后停止。

## 唯一主动改变的训练因素

基线为 phase_b_sft_seed20261026，训练 seed 同为 20261026。从原始 Qwen3-8B 初始化新的 LoRA 和 Adam，不加载旧检查点、不复用轨迹或评分。90题/轮、5题/批、每题一条在线完整轨迹，18批/轮；沿用相同任务顺序及派生 rollout seed。Codex 使用相同 v7 rubric prompt，仅 F=0 且 P>=3 的步骤进入 SFT。LoRA、loss、生成和评估配置保持一致。
前5次有效更新与基线完全相同：1e-5、2e-5、3e-5、4e-5、5e-5。之后按有效更新次数平滑余弦衰减，第54次为5e-6。没有 warm restart；空 batch 不更新优化器，也不推进衰减。每轮更新进度以检查点中的 optimizer_updates 为准，重启进程不会重置曲线。
`lr(u)=5e-6+(5e-5-5e-6)*(1+cos(pi*(u-5)/49))/2`，用于 u=6..54。若出现空 batch，54批内实际有效更新少于54，则终值尚未达到5e-6；不为凑终值添加训练批次。
网络恢复使用基线实验修复后的流程。仅监控、报告和模型保留策略有管理性变更，不改变梯度或采样分布。Codex 无可固定的评分 seed；相同训练 seed 也不能保证外部评分和 GPU 计算逐位一致。模型分叉后在线轨迹自然变化，属于学习率变化的下游结果。

## 学习率计划

| 更新次数 | 阶段 | 学习率 |
|---:|---|---:|
| 1 | 首次更新 | 1e-05 |
| 5 | warmup结束 | 5e-05 |
| 18 | 第一轮末 | 4.262677e-05 |
| 36 | 第二轮末 | 1.83923748e-05 |
| 54 | 第三轮末 | 5e-06 |

## 同 seed 正式 dev57 对照

| 学习率 | 轮次 | 成功题数 | Macro | 通过检查 | 纯文档占比 | 重复文档占比 | 业务步骤 | 无代码终止 | 平均步骤 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 恒定 | 1 | 6/57 | 42.34% | 106/291 | 26.17% | 17.11% | 553 | 8/57 | 24.81 |
| 恒定 | 2 | 8/57 | 40.49% | 103/291 | 75.30% | 53.41% | 131 | 3/57 | 31.11 |
| 恒定 | 3 | 1/57 | 26.73% | 55/291 | 77.76% | 27.70% | 20 | 50/57 | 13.49 |
| 余弦 | 1 | 13/57 | 57.24% | 158/291 | 27.66% | 9.75% | 574 | 3/57 | 21.95 |
| 余弦 | 2 | 15/57 | 58.06% | 156/291 | 45.57% | 22.95% | 348 | 1/57 | 26.14 |
| 余弦 | 3 | 14/57 | 54.41% | 145/291 | 50.59% | 26.95% | 391 | 0/57 | 28.12 |

全部评估使用 dev57、temperature=0、seed=100、无反馈学生策略和官方终态检查。重复文档按同一轨迹中相同 Python AST 计数；业务动作排除文档、Supervisor 和 login/logout。出现 API 代码不保证调用成功。

## 入选训练样本

| 轮次 | 批数 | 全步骤 | SFT步骤 | 文档SFT | 业务SFT | 重复文档SFT | 平均batch loss |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 18/18 | 1703 | 363 | 229 | 49 | 7 | 0.129586 |
| 2 | 18/18 | 1783 | 670 | 451 | 88 | 18 | 0.110632 |
| 3 | 18/18 | 2346 | 1119 | 598 | 215 | 24 | 0.101671 |

每轮数据在线重采，loss不是固定验证集指标；不根据训练loss判断任务能力。

## 同轮次逐题比较

第1轮余弦相对恒定：成功 +7 题，Macro +14.90 个百分点，重复文档 -7.36 个百分点，业务步骤 +21，无代码终止 -5 题；新增成功 9、丢失成功 2，检查新增 69、丢失 17。
第2轮余弦相对恒定：成功 +7 题，Macro +17.57 个百分点，重复文档 -30.46 个百分点，业务步骤 +217，无代码终止 -2 题；新增成功 8、丢失成功 1，检查新增 69、丢失 16。
第3轮余弦相对恒定：成功 +13 题，Macro +27.68 个百分点，重复文档 -0.75 个百分点，业务步骤 +371，无代码终止 -50 题；新增成功 13、丢失成功 0，检查新增 90、丢失 0。

即使较恒定学习率更好，也需同时判断是否保留早期能力、是否仅延迟退化。该实验同时降低了后期学习率和累计学习率，不能单独证明余弦形状优于所有低恒定学习率。单个seed与57题不足以确立稳定泛化收益。

## 固定案例

| 分支 | 案例 | 第1轮：检查；重复/全部步；终止 | 第2轮 | 第3轮 |
|---|---|---|---|---|
| 恒定 | b119b1f_2 | 6/6；0/13；completion_api | 0/6；18/23；context_limit | 0/6；0/7；no_python_code |
| 恒定 | d4e9306_2 | 2/6；0/10；completion_api | 1/6；12/13；context_limit | 1/6；0/7；no_python_code |
| 恒定 | 6c2c621_1 | 1/8；0/50；step_limit | 1/8；20/50；step_limit | 1/8；8/23；no_python_code |
| 恒定 | 396c5a2_1 | 0/6；1/11；completion_api | 0/6；23/31；context_limit | 0/6；0/8；no_python_code |
| 恒定 | 23cf851_1 | 2/2；1/10；completion_api | 2/2；4/19；completion_api | 1/2；0/11；no_python_code |
| 余弦 | b119b1f_2 | 6/6；0/14；completion_api | 0/6；11/14；context_limit | 6/6；1/21；completion_api |
| 余弦 | d4e9306_2 | 6/6；0/12；completion_api | 6/6；0/13；completion_api | 6/6；1/18；completion_api |
| 余弦 | 6c2c621_1 | 6/8；1/20；completion_api | 6/8；3/26；completion_api | 8/8；4/29；completion_api |
| 余弦 | 396c5a2_1 | 5/6；0/12；completion_api | 5/6；2/15；completion_api | 1/6；4/12；completion_api |
| 余弦 | 23cf851_1 | 1/2；0/10；completion_api | 2/2；1/15；completion_api | 2/2；1/16；completion_api |

## 验收和保存

首批已验收：loss=0.081313，梯度=0.278900，lr=1.0e-05，SDPO loss/梯度=0，显存峰值=23.41 GiB。
只保留最新完整检查点及已评估最优轮次（先比较成功题数，再比较Macro，同分选更早轮次），重合时只保留一份；写入新检查点期间会短暂多一份。全部轨迹、评分、dataset、指标与官方报告保留。仅清理本余弦实验的权重，原实验不动。
[实时状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/STATUS.json) · [心跳](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/heartbeat.json) · [预检](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/preflight.json) · [汇总](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/lr_summary.json) · [逐批指标](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/training_metrics.csv) · [同轮逐题比较](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/paired_schedules.csv)

![学习率对照](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/lr_comparison.png)
