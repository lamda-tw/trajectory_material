# 实验审查入口

> **同历史协议五点评测已完成**（2026-10-16T12:29:59.780214+08:00）：step 0: TGC 25/57、SGC 4/19；step 1: TGC 18/57、SGC 3/19；step 5: TGC 18/57、SGC 2/19；step 10: TGC 20/57、SGC 3/19；step 15: TGC 23/57、SGC 3/19。详见 [五点趋势与逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/evaluation/historical_protocol_trend/COMPARISON.md)。

> **2026-10-16 10:28：同历史协议的step 0复测完成。** TGC=25/57（43.86%），SGC=4/19（21.05%），evaluator通过204/291、失败87。用户接受同模型输出波动，后续step 1、5、10、15以本次GPU1复测作对照，已自动继续。详见 [持续更新的对比报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/evaluation/historical_protocol_trend/COMPARISON.md)。

> **2026-10-16 10:00：已启动同历史协议的五点DEV57评测（step 0、1、5、10、15）。** 复用训练前原始评测脚本和配置，先核对step 0复现，再依次测试四个checkpoint。全部在GPU1、既有实验目录内执行；不启动训练。参见 [执行方案与实时进度](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/HISTORICAL_DEV57_RUN.md)。下文20/57属于另一评测入口的历史结果，不混入本次曲线。

> **2026-10-16 基线对比补充：TGC 23/57（40.35%）→20/57（35.09%）；SGC 4/19（21.05%）→2/19（10.53%）。** 新增成功6题、丢失成功9题，实测指标下降。训练前历史LoRA与本次起点一致，但评测入口存在提示空白、thinking和上下文预算差异，尚未进行同入口A0复测，不能将下降完全归因于训练。详见 [逐题对比与协议核对](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/evaluation/round_01_final/BASELINE_COMPARISON.md)。没有启动重跑或下一轮训练。

> **2026-10-16 最新结果：第一轮训练与最终模型DEV57评测均已完成。DEV57成功20/57，TGC=35.09%。** 评测于09:35结束，完整性核对通过，GPU1服务已退出。结果全部集中在原实验目录的 [逐题结果表](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/evaluation/round_01_final/RESULTS.md)，协议与验收见 [DEV57运行记录](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/DEV57_RUN.md)。未运行初始模型对照，不声明相对提升；没有启动后续训练。

> **2026-10-15 最新决定：优化留作之后改进，本次不启用。** 当前GPU1训练按原配置继续，完成15批并保存模型后结束。调查与候选步骤已保存至 [优化留档](/root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/OPTIMIZATION_NOTES.md)，没有安排自动切换或优化版重跑。

> **当前安排（2026-10-15）：完成正在运行的15批单轮，保存最终LoRA后结束。** 取消后续重复训练、备选重跑与DEV57。原GPU1训练进程持续运行；实时批次见 [运行记录](ROUND_01_RUN.md)，完整变更见 [当前执行范围](SINGLE_POOL_MODEL_SCOPE.md)。下文2026-10-14的自动链是历史记录。

> 已于北京时间 2026-10-14 17:19 启动第一轮自动执行链，起始阶段为完整池参考概率计算与工程试跑。正式参数更新需在试跑、冻结和初始基线通过后自动开始。实时状态见 [运行记录](ROUND_01_RUN.md)。


> 第一轮已获执行授权。新增自动流程与参数来源见 [ROUND_01_EXECUTION.md](ROUND_01_EXECUTION.md)，实时执行记录见 [ROUND_01_RUN.md](ROUND_01_RUN.md)。下文第4步记录是此前已完成的基础验收，不代表当前排队阶段均已完成。


更新：2026-10-14（北京时间）。第 1—3 步已执行完成：独立目录、预检、正式筛选和完整 SFT 编码数据均已验收。第 4 步核心实现与 CPU/GPU1 基础验收完成；整池稳定性试跑、基线和正式训练未执行。

建议按以下顺序审查：

1. [PLAN.md](PLAN.md)：实验目标、已完成评分、唯一筛选规则、联合训练设计和结论边界。
2. [EXECUTION_STEPS.md](EXECUTION_STEPS.md)：具体操作手册，尤其步骤 2 的唯一筛选、步骤 3 的完整响应监督、步骤 4 的数学实现、步骤 8 的一次联合更新及步骤 11 的恢复语义。
3. [TRAINING_CONFIG_DRAFT.json](TRAINING_CONFIG_DRAFT.json)：候选数值、预算、测量项与冻结要求。

当前已完成：540 条评分、9,886 步总分及正式选样；唯一条件 P−F≥4，选中 2,623 步、排除 7,263 步，无额外质量过滤。详见 [第 1、2 步执行记录](STEP_01_02_RESULTS.md) 和 [第 3 步数据构建记录](STEP_03_RESULTS.md)。单遍监督量 205,238 token，五遍 1,026,190，最长完整样本 31,814 token。

**资源限制：仅物理 GPU1；GPU0 留给同事。** 已写入计划、实验 draft 与独立 resource_policy，并提供固定 GPU1 UUID 的启动器。后续训练、推理、reference、smoke 和评测均须遵守；world_size=1，DDP 禁用。

| 执行步骤 | 具体工作 | 当前状态 |
| --- | --- | --- |
| 1 | 独立目录、来源哈希、初始 adapter、环境和资源预检 | **已完成，预检通过** |
| 2 | 复算净分并生成正式选中/未选清单 | **已完成，2,623 步，独立复核通过** |
| 3 | 原始上下文/完整响应构建、token 编码、mask 与 T_SFT 验收 | **已完成，2,623 样本，205,238 目标 token** |
| 4 | 实现联合 trainer/采集器，验证梯度、归约和恢复 | 核心与基础集成通过；见 STEP_04_RESULTS.md |
| 5 | 编排五遍 SFT 与全部在线任务批次 | 待执行 |
| 6 | 独立 smoke、资源测量、正式配置冻结 | 待执行 |
| 7 | 初始 checkpoint 的同协议 DEV57 基线 | 待执行 |
| 8 | 首批新采样 + RL/SFT 梯度合并 + 一次 LoRA 更新 | 待执行 |
| 9 | 第 1 轮完成、预算验收及 DEV57 | 待执行 |
| 10 | 第 2—5 轮，保存模型，第 3/5 轮 DEV57 | 待执行 |
| 11 | 按已提交状态恢复各类故障 | 运行期适用 |
| 12 | 最终覆盖/预算/模型验收与报告 | 待执行 |

候选主预算：5 轮 RL 池 × 90 题 × 每题 6 条 = 2,700 条消费，首轮复用 540、新采 2,160；每批 6 题且 K=1 时共 75 次联合更新。局部 SFT 全部 2,623 步学习 5 遍，五遍实际监督 token 为 1,026,190。后续仅在 GPU1 上测量资源；工程检查导致候选批量配置改变时，必须同步重算预算并保存理由。

当前实施结果见 [STEP_04_RESULTS.md](STEP_04_RESULTS.md)。联合训练器、整池采集器和候选调度已实现，2 次 GPU1 隔离更新通过。用户已确认整池采集、池内单遍分批更新、轮间换池；每批完成后更新参数，整轮完成后才重新采集。SFT 每步目标 token 内平均，再对步骤平均。

15 批仍为待完整池试跑验证的候选，由 agent 根据 GPU1 实测自行决定；当前 lambda=0.1、KL=0.01、共享峰值 LR=5e-6。下一步是完整池的策略偏离与耗时试跑、正式概率容差、配置冻结及初始 DEV57。基座冻结，续训已有 LoRA，轮次边界不重置 optimizer/LR。现有 SFT 数据、源模型和其他实验未改动。

## 随时查看轮次与 batch

下面的命令每5秒刷新一次，按 Ctrl+C 只退出查看，不停止实验：

```bash
python /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/show_progress.py --watch 5
```

它集中显示工程试跑/正式训练、当前轮次与 batch、RL/SFT 分支、已提交更新数、参考缓存进度和进程心跳。`full_pool_trial_15` 是正式第一轮之前的整池试跑，不代表正式第一轮已经更新；`formal_round_01` 才是正式训练。
