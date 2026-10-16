# AppWorld：初始 SFT LoRA 上的整池 RL + 固定步骤 SFT

> **同历史协议五点评测已完成**（2026-10-16T12:29:59.780021+08:00）：step 0: TGC 25/57、SGC 4/19；step 1: TGC 18/57、SGC 3/19；step 5: TGC 18/57、SGC 2/19；step 10: TGC 20/57、SGC 3/19；step 15: TGC 23/57、SGC 3/19。详见 [五点趋势与逐题对照](evaluation/historical_protocol_trend/COMPARISON.md)。

> **2026-10-16 10:28：同历史协议的step 0复测完成。** TGC=25/57（43.86%），SGC=4/19（21.05%），evaluator通过204/291、失败87。用户接受同模型输出波动，后续step 1、5、10、15以本次GPU1复测作对照，已自动继续。详见 [持续更新的对比报告](evaluation/historical_protocol_trend/COMPARISON.md)。

> **2026-10-16 10:00：已启动同历史协议的五点DEV57评测（step 0、1、5、10、15）。** 复用训练前原始评测脚本和配置，先核对step 0复现，再依次测试四个checkpoint。全部在GPU1、既有实验目录内执行；不启动训练。参见 [执行方案与实时进度](HISTORICAL_DEV57_RUN.md)。下文20/57属于另一评测入口的历史结果，不混入本次曲线。

> **2026-10-16 基线对比补充：TGC 23/57（40.35%）→20/57（35.09%）；SGC 4/19（21.05%）→2/19（10.53%）。** 新增成功6题、丢失成功9题，实测指标下降。训练前历史LoRA与本次起点一致，但评测入口存在提示空白、thinking和上下文预算差异，尚未进行同入口A0复测，不能将下降完全归因于训练。详见 [逐题对比与协议核对](evaluation/round_01_final/BASELINE_COMPARISON.md)。没有启动重跑或下一轮训练。

> **2026-10-16 最新结果：第一轮训练与最终模型DEV57评测均已完成。DEV57成功20/57，TGC=35.09%。** 评测于09:35结束，完整性核对通过，GPU1服务已退出。查看 [逐题结果表](evaluation/round_01_final/RESULTS.md)、[CSV](evaluation/round_01_final/task_results.csv)、[评测记录](DEV57_RUN.md)。下方此前取消DEV57等文字保留为历史记录；没有启动后续训练或优化版重跑。

> **2026-10-15 最新决定：优化留作之后改进，本次不启用。** 当前GPU1训练按原配置继续，完成15批并保存模型后结束。前缀共享调查、CPU原型及尚未完成的验收见 [优化留档](OPTIMIZATION_NOTES.md)；没有安排自动切换或优化版重跑。

> **当前安排（2026-10-15）：完成正在运行的15批单轮，保存最终LoRA后结束。** 取消后续重复训练、备选重跑与DEV57。原GPU1训练进程持续运行；实时批次见 [运行记录](ROUND_01_RUN.md)，完整变更见 [当前执行范围](SINGLE_POOL_MODEL_SCOPE.md)。下文2026-10-14的自动链是历史记录。

> 已于北京时间 2026-10-14 17:19 启动第一轮自动执行链，起始阶段为完整池参考概率计算与工程试跑。正式参数更新需在试跑、冻结和初始基线通过后自动开始。实时状态见 [运行记录](ROUND_01_RUN.md)。


> 第一轮已获执行授权。新增自动流程与参数来源见 [ROUND_01_EXECUTION.md](ROUND_01_EXECUTION.md)，实时执行记录见 [ROUND_01_RUN.md](ROUND_01_RUN.md)。下文第4步记录是此前已完成的基础验收，不代表当前排队阶段均已完成。


2026-10-14（北京时间）：第 1—3 步数据准备完成；第 4 步联合训练器与采集接口已实现，CPU 数学测试和 GPU1 基础集成试跑通过。**正式训练未启动，15 批尚未冻结。**

当前策略：一轮固定模型采集 540 条，池内单遍分批联合训练，**每批结束更新参数**；全部用完后才采下一池。首轮复用现有 540 条，后四轮各新采 540 条。固定 2,623 个 SFT 步骤每轮完整学习一遍，loss 先在每步目标 token 内平均，再对步骤平均。仅续训原有 LoRA，基座冻结。

**资源硬限制：仅物理 GPU1，GPU0 留给同事。** 使用 `scripts/gpu1_run.py`，不覆盖其 UUID 环境。GPU 阶段互斥，进程内 cuda:0 为物理 GPU1；DDP 禁用。

## 审查入口

- [第 4 步实现、实测结果与未完成项](STEP_04_RESULTS.md)
- [当前候选配置指针](config/current_draft.json) · [整池训练配置](config/pool_training_draft.json)
- [首轮完整 540 池](rollout/round_01/pool.json)
- [具体候选任务/SFT 更新清单](data/sft_schedule_candidate.jsonl) · [预算验收](checks/schedule_candidate.json)
- [数学与恢复测试](checks/joint_math.json) · [真实采集验证](checks/collection_protocol.json)
- [最长样本 GPU1 实测](smoke/gpu_probe/report.json) · [真实联合更新/重载](smoke/joint_integration/report.json)
- [概率差异实测](checks/logprob_alignment.json) · [GPU1 互斥验证](checks/gpu1_lock.json)
- [总计划](/root/autodl-tmp/workspace-tw/plans/2026-10-13_appworld_sft_init_local_sft_online_rl/PLAN.md) · [逐步执行手册](/root/autodl-tmp/workspace-tw/plans/2026-10-13_appworld_sft_init_local_sft_online_rl/EXECUTION_STEPS.md)

## 数据与历史记录

唯一入选条件为 P−F≥4，无额外质量过滤或内容去重。2,623 步、205,238 目标 token/遍，最长完整输入 31,814 token。RL 仍使用完整任务组的全部轨迹，不以该步骤分数筛选。

- [完整 SFT 数据清单](data/data_manifest.json) · [格式与使用](data/README.md)
- [正式选样](data/selected_steps.jsonl) · [全量选样决定](data/selection_decisions.jsonl)
- [预检](checks/preflight.json) · [mask 验收](checks/token_mask.json)
- [GPU1 资源约束](config/resource_policy.json)

config/draft.json 及 step03/step_equal 配置、STEP_03_MANIFEST.json 都是历史快照。已验收的样本/编码/mask 未修改。第 4 步快照见 STEP_04_MANIFEST.json。

## 下一阶段

在 GPU1 上完成完整池更新阶段的漂移与耗时检查，由 agent 决定有效批量和每池更新次数；确定服务/训练概率容差，补齐轮间编排及评测，然后冻结正式配置并运行初始 DEV57。当前 15 批、lambda=0.1、KL=0.01、共享峰值 LR=5e-6 是工程候选，不能把小池通过当成已验证最优。

## 随时查看轮次与 batch

下面的命令每5秒刷新一次，按 Ctrl+C 只退出查看，不停止实验：

```bash
python /root/autodl-tmp/workspace-tw/experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/scripts/show_progress.py --watch 5
```

它集中显示工程试跑/正式训练、当前轮次与 batch、RL/SFT 分支、已提交更新数、参考缓存进度和进程心跳。`full_pool_trial_15` 是正式第一轮之前的整池试跑，不代表正式第一轮已经更新；`formal_round_01` 才是正式训练。

训练耗时的CPU核算见 [training_cost_analysis.json](checks/training_cost_analysis.json)：整轮12,509次主前向/反向调用，累计127,035,930个主干token位置（含重复前缀，不含checkpoint重算）。这是输入与时间核算，不是GPU kernel profiler或已验证的加速倍数。当前训练实现未改动。
