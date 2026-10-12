# SFT LoRA 起点：train90 采样结果

## 2026-10-11：test_normal168 评测与原因分析已完成

完整 **168/168** 题已按 2026-09-23 参考协议完成，两张卡各运行 84 题，官方全量聚合于 **2026-10-11 19:00（北京时间）** 完成。模型仍为完整 train90 × 6 单次更新得到的 step06 LoRA；本次未追加训练。两个评测分片均正常退出，全部首次提示词及固定请求字段与历史对照一致，模型 SHA 核验通过。补充只读诊断完成后，两张 GPU 均已释放。

| test_normal 模型 | 成功任务 | TGC | SGC |
|---|---:|---:|---:|
| 更新前 SFT LoRA（历史） | 51/168 | 30.4% | 16.1% |
| 静态 rubric GRPO 单次更新 | **37/168** | **22.0%** | **16.1%** |
| 参考全参数 SFT（历史） | 28/168 | 16.7% | 5.4% |

相对初始 LoRA，新增成功 7 题、退化 21 题，净减少 14 题，TGC 下降 8.3 个百分点。21 道退化题均有提交动作但未满足全部条件，16 道只少通过一项；没有退化题因上下文中断。条件通过数 598 → 594；完整成功场景均为 9/56，但场景身份有变化。此前同一模型的 dev57 为 23/57 → 16/57。

训练审计未发现多次 step、梯度合并或保存错模型的证据。静态奖励整体与成功相关，但 280 条正优势轨迹中有 122 条官方失败，27 条成功轨迹为负优势；整条轨迹统一优势会把正确与错误步骤一起加权。首步 KL 的值和梯度在起点均为零。固定训练 probe 测得更新后条件分布确有变化，但不足以证明学习率过大；各机制的因果贡献仍需 Dev 对照，不能归结为单一原因。

[完整 test 报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/REPORT.md) · [训练原因分析](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/TRAINING_DIAGNOSIS.md) · [成对轨迹案例](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/CASE_STUDIES.md) · [168 题全部输入输出](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/TASKS.md) · [逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/task_comparison.csv)。下方保留此前阶段记录。

## 2026-10-11：全量单次更新和 dev57 已完成

北京时间 2026-10-11 06:39，完整 **90 题 × 6 = 540 条** 的梯度已在两张卡上算完并合并，完成 **1 个 PPO epoch、1 次 optimizer step**。policy 权重已变化，reference 未变化；保存重载 logprob 最大误差为 0。checkpoint 三个文件 SHA-256 与训练来源已核验。

最终模型为 Qwen3-8B 基座加 [step06 LoRA checkpoint](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1/checkpoint)。原单卡/五轮入口不再执行。

用户要求的完整 dev57 评测于 **2026-10-11 17:54** 结束。复用 2026-09-23 参考实验的官方 57 题、ReAct 提示词、temperature=0、seed=100、50 步、3000 输出 tokens、32000 窗口及无 reasoning parser 的历史 dev 协议；耗时 31.0 分钟。每题仅运行一次，57 个唯一结果与官方聚合完全一致，无评分器或基础设施故障；7 题上下文超限按原协议保留。

| 模型 | 成功任务 | TGC | SGC |
|---|---:|---:|---:|
| 更新前 SFT LoRA（历史） | 23/57 | 40.4% | 21.1% |
| 本次静态 rubric GRPO 单次更新 | 16/57 | 28.1% | 10.5% |
| 参考全参数 SFT（历史） | 12/57 | 21.1% | 0.0% |

相对更新前 LoRA，新增成功 4 题、退化 11 题，净减少 7 题，TGC 下降 12.3 个百分点。该次评测未观察到提升；这是单次更新及历史对照的结果，不代表完整 DRACO 训练效果。

[完整评测报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_dev57/REPORT.md) · [逐题输入输出](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_dev57/TASKS.md) · [逐题对照 CSV](/root/autodl-tmp/workspace-tw/experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_dev57/task_comparison.csv)。下方内容为此前阶段的历史记录，以本节为当前状态。

## 最新执行：GPU 0、1 并行，完整 540 条仍只更新一次

2026-10-10 用户授权两张卡同时使用。已停止尚未提交更新的单卡运行：当时只处理到第 1 条轨迹第 10 个步骤、约 96 秒，optimizer step 为 0；该段梯度重新计算，日志保留在 step04 的 orchestration/parallel_transition。原 540 条评分及 batch SHA256 `b02e408209a09bef3b5b83664aca325b30f3ba70b4506340895b769dc169a670` 保持不变，不重新采样或评分。

新增独立两卡执行阶段：每卡分配 **45 题、270 条轨迹**，GPU 0/1 分别覆盖 885,969 / 899,755 个生成 token。每条 loss 继续除以全局 540 和本条 token 数，两卡只累计梯度；全部完成后对梯度求和，统一裁剪并执行 **一次 optimizer.step、一个 PPO epoch**。每卡每完成六条保存累计梯度与 RNG，可从最近完整组恢复。计算顺序变化允许浮点舍入差异，CPU 小模型验证梯度及更新数值一致。

5 项 CPU 检查通过，真实两卡执行器已启动。新模型提交到 `/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1/checkpoint`，成功后写 evaluation_target.json；这是新的活动输出目录，旧单卡路径不再产出模型。实时进度以运行状态为准，不将启动等同于更新完成。

[两卡执行说明](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step06_train90_two_gpu/README.md) · [实时状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1/STATUS.md) · [任务分配与冻结清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1/manifest.json) · [CPU 验证](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1/validation.json)

## 最新完成：train90 全量静态评分

**2026-10-10 15:24（北京时间）：全量评分已完成并核验，540/540 条、90/90 个完整六条组。** 网络中断后保留原 312 条有效评分并补齐 228 条，原评分 SHA256 全部未改动；共 11,340 项规则判定。输入来源、评分请求/响应一致性和每题 reward/advantage 重算均通过，90 组均有非零优势。全量 batch 已生成，readiness 的待评分数为 0。训练继续按原定单次更新及 GPU 空闲门槛执行，不再调用 judge。

[评分完成记录](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/scoring_completion.json) · [逐题/逐次输入输出索引](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/score_index.json) · [reward 明细](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/rubric/update_001/reward_summary.json) · [实时执行阶段](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/orchestration/status.json)

## 历史工程验证（2026-10-09）：DRACO 静态 GRPO 闭环

2026-10-09：新题评分 **18/18**、378 项判定、3 个完整组；GPU 1 完成 Qwen3-8B SFT LoRA **一次真实更新**，policy 权重发生变化、初始 SFT reference 保持冻结、保存重载 logprob 检查通过。未运行全量 540 评分或 dev57，不据此宣称效果提升。

[本次完整工程报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1/FRAMEWORK_REPORT.md) · [框架入口](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step03_grpo_framework/README.md) · [训练 checkpoint](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1/rubric/update_001/checkpoint)

更新：2026-10-09。**完整 train90 × 6 = 540 条轨迹已完成并验收。** 官方 train 终态成功 186/540；23 个全失败组、63 个成功/失败混合组、4 个全成功组。这些是训练内采样统计，不是 dev 成绩。

采样之后，已完成 12 条静态 rubric smoke、同批校准重测及证据复核；校准重测的工程验收通过，语义验收仍有问题。尚无 GRPO 更新或新 dev 结果。后台采样已结束。完整过程见 [实验报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)。

## 执行记录

策略为 Qwen3-8B + 现有 train90 / epoch5 LoRA，rank 8、alpha 16。使用 GPU 0、独立端口 8129，任务、六个 seed、prompt、parser、解码参数与预算均与 raw 分支配对。

昨夜因 AppWorld 无法序列化 Python Ellipsis 日志参数而中断。2026-10-09 完成日志兼容修复，保留原有 342 条轨迹不变，补齐 198 条；模型动作、真实环境反馈与官方终态评价保持原协议。全部 540 条通过 token 重建、old logprob 对齐与完整性验收。

已执行的采样命令为 `python -u step01_collect.py --execute`，当前无需重复启动。历史 supervisor 最多尝试三次；恢复记录和修复前快照保存在 recovery/2026-10-09/。

## 结果与来源

- [最终统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/summary.json)
- [完整验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/collection_validation.json)
- [轨迹索引](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectory_index.json)
- [两分支采样统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/collection_comparison.json)
- [恢复与最终诊断](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/recovery/2026-10-09/final_diagnostics.json)
- [冻结初始 adapter](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/initial_adapter)
- [采样任务清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/planned_jobs.json)

本目录已有采样和验收入口、静态规则与 judge 模块，尚无经过真实更新验证的 LoRA GRPO 续训入口。config 中继承的旧训练预算不是已执行记录。COMPARISON.md 的有效内容已并入 plans；来源快照中的历史副本保留原样。

后续安排统一见 [当前待办](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/README.md) 与 [实验计划](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md)。实验报告仅存放在本实验目录。

2026-10-09 新增记录：[静态评分 smoke](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v2/SMOKE_REPORT.md) 已完成 12 条 / 252 项判定。工程验收通过，发现 NA 口径与实际执行证据问题，原始评分保留，尚未训练。

2026-10-09 校准重测记录：[v3 报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/SMOKE_REPORT.md) 已完成相同 12 条 / 252 项，PASS 137 / FAIL 78 / NA 37，12 次调用、无重试。上轮四处明确问题得到纠正，但仍发现未执行分页被用作 PASS 依据，尚未通过语义验收。完整的 [六条轨迹 reward 计算](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/REWARD_WORKED_EXAMPLE.md) 也已收入主实验报告。两版原始评分都保留，当前没有后台评分或训练任务。

2026-10-09 当前配置已退回官方静态基线加原协议适配，v3 校准约束不参与主线。三个新题共 18 条输入已冻结；启动遇到当前执行环境认证失败，已停止，有效评分 0/18。用户确认其终端 Codex 可用，环境差异排查尚未完成。详见 [启动记录](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/SMOKE_REPORT.md)。
