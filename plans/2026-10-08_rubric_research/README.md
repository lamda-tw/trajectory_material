# 当前主线：DRACO 静态轨迹评分 → reward → GRPO

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

## 单卡安排（执行方式已改为上方两卡方案）

**2026-10-10 15:24（北京时间）：全量评分已完成并核验，540/540 条、90/90 个完整六条组。** 网络中断后保留原 312 条有效评分并补齐 228 条，原评分 SHA256 全部未改动；共 11,340 项规则判定。输入来源、评分请求/响应一致性和每题 reward/advantage 重算均通过，90 组均有非零优势。全量 batch 已生成，readiness 的待评分数为 0。训练继续按原定单次更新及 GPU 空闲门槛执行，不再调用 judge。

[评分完成记录](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/scoring_completion.json) · [逐题/逐次输入输出索引](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/score_index.json) · [reward 明细](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/rubric/update_001/reward_summary.json) · [实时执行阶段](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/orchestration/status.json)

2026-10-10 用户撤回固定数据五轮方案，改为只做通完整训练集的静态 rubric → reward → GRPO → 保存模型流程。保持 **90 题 × 6 条 = 540 条**；使用已完成的全量评分，其中包括原 18 条有效缓存和已补齐的有效记录。在每题六条内部独立计算过滤后的 reward 和 advantage。所有 540 条累计梯度后执行 **一个 PPO epoch、一次 optimizer step**，随后结束；本次不再采样、不再做第二轮更新，也不自动评测。

policy 从生成这些轨迹的初始 SFT LoRA 开始，新建 optimizer；reference 单独加载并冻结同一初始模型。不会接着先前三题评分/单题更新的工程 checkpoint 训练。该实验覆盖静态方法的首次更新链路，不能当作论文完整多步训练或效果复现。

已启动轻量等待执行器：先等待当前评分进程释放共享锁，再严格验证全部 540 条评分和完整 90 组。随后仅在 **GPU 1 无计算进程、空闲显存至少 80 GiB，连续三次间隔 60 秒检查均满足** 时启动训练；其他任务占用时继续等待。准备和评分阶段不加载模型、不分配 GPU。旧五轮等待进程已停止，五轮方案没有执行真实训练。

训练结束后保存独立 LoRA adapter、optimizer/RNG、指标和来源清单，验证保存重载后的真实 token logprob 一致，再写出后续评测加载说明。目标目录为 `/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/rubric/update_001/checkpoint`；与基础 Qwen3-8B 一起加载。已有有效 checkpoint 会被验证并跳过，不重复更新。整批梯度计算中断而尚未提交 checkpoint 时，需要从初始模型重算这一批。

[执行说明与控制](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/orchestration/README.md) · [执行状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/orchestration/status.json) · [实时评分/训练监控](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step05_offline_ppo5_v1/monitoring/STATUS.md)。6 项纯 CPU 等待与启动测试通过，未为准备工作加载 GPU 模型。以下是历史方案记录；以本节为当前执行范围。

## 历史方案（已取消）：固定 540 条、五轮离线 PPO；GPU 使用暂停

2026-10-10 用户因训练资源不足，明确选择完整 train90（90×6）固定数据训练五遍。先复用 18 条有效评分并补评 522 条，在每题六条内部计算一次 reward 和 advantage，随后固定数据、评分、优势及原始 old logprob 做五个 PPO epoch。每遍完整累计 540 条梯度后更新一次，共五次 optimizer step；policy/optimizer 连续，reference 始终是初始 SFT 模型。此方案明确是离线更新实验，不声称复现 DRACO 的在线重采样循环。

用户随后明确要求**先不要占用 GPU，别人正在训练**。本次只继续补评分、准备入口及 CPU 小模型验证；不启动 8B、不执行真实 GPU backward，也不在 GPU 空闲后自动训练。只有用户后续明确放开 GPU 使用，才执行五轮训练。评分完成只提交固定 batch，结束于 training_on_hold 状态。

独立阶段为 [step05_offline_ppo5](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step05_offline_ppo5/README.md)，运行产物在 [step05_offline_ppo5_v1](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step05_offline_ppo5_v1)。12 项 CPU/标准库测试已通过，覆盖五轮 optimizer 续接、初始行为概率不变、reference 冻结、缓存校验与逐组梯度恢复。全部 540 条输入核验通过；实际 8B 五轮训练和新 dev 评估尚未执行。

补评分已由旧 step04 的 score-only 入口启动；新阶段的 score-only driver 通过共享锁等待其结束，再校验/补齐缓存并生成五轮固定 batch，不并发重复评分，不接入训练。实时状态见 [status.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step05_offline_ppo5_v1/status.json)，已有 score 计数以 judgement 文件和日志为准。

以上五轮方案已由本文最上方的单次更新方案替代；保留为历史记录。

## 历史准备（2026-10-09）：完整 train90 单次更新，暂不执行

2026-10-09 用户要求先做好准备，等待后续指令。准确区分已有结果：**3 题 × 6 条已评分；实际 GRPO 仅使用其中 afc0fce_1 的 6 条，累计梯度后做过一次 optimizer step。**

下一步已准备独立入口：完整 **90 题 × 6 条 = 540 条**；18 条当前基线评分通过复用校验，另 522 条待评。按每题六条计算过滤后的静态 reward 和组内 advantage；所有 540 条累计梯度后仅做 **一次 optimizer step、一个 PPO epoch**。这一全批次安排不同于把旧入口运行 90 次更新。

本阶段重新从生成这些轨迹的冻结初始 SFT LoRA 起步并新建 optimizer；reference 单独加载并冻结同一初始 SFT 模型。90×6 全部来源、SHA256、token/logprob 对齐及训练集范围检查通过：9,886 个生成步骤、1,785,724 个生成 token，最长上下文 32,000。GPU 延续本次已授权的 GPU 1，正式启动时重新检查资源。

**本次仅准备和离线验收：没有新增 judge 调用、模型加载或反向传播；全量 batch 和 checkpoint 均未生成。** 5 项纯标准库测试通过，训练器沿用已验证的原实现。按用户要求等待，不自动执行后续命令。今后第二次更新需要从更新后的策略重新采样。

[独立入口与待执行命令](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step04_train90_single_update/README.md) · [准备状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/readiness.json)。下方保留之前阶段的历史记录，本轮执行范围以本节为准。

## 本次已完成：DRACO 静态 GRPO 工程闭环

2026-10-09：新题评分 **18/18**、378 项判定、3 个完整组；GPU 1 完成 Qwen3-8B SFT LoRA **一次真实更新**，policy 权重发生变化、初始 SFT reference 保持冻结、保存重载 logprob 检查通过。未运行全量 540 评分或 dev57，不据此宣称效果提升。

[本次完整工程报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1/FRAMEWORK_REPORT.md) · [框架入口](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step03_grpo_framework/README.md) · [训练 checkpoint](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1/rubric/update_001/checkpoint)

更新：2026-10-09。按用户最新要求，优先做通原方法的评分与训练链路。官方 21 条规则、评分正文和 reward 公式固定，不继续逐题调提示，不把 judge 零错误作为训练前提。

本次恢复此前固定的三个新 train 题、共 18 条评分。Codex 已登录且升级为 0.162.0，使用新运行目录保留旧认证失败日志。已修复“重连后成功完成仍被旧审计器判为失败”的兼容问题，保留最早有效响应。

独立 GRPO 框架已实现。首次更新固定为 afc0fce_1 的六条轨迹；单个完整组、一个 PPO epoch、一次 optimizer step，用于工程验证。用户本次明确允许 GPU 1，覆盖先前只用 GPU 0 的安排。真实 8B 前向预检已通过，包括 32000 上下文、独立冻结 SFT reference 和旧 logprob 一致性。评分与实际更新的完成状态以运行产物为准。

reward 保留同题六条中至少一次 FAIL 的规则，计算 `R=10*(P-F)/(P+F)`，NA 不计分母。GRPO 只对生成 token 计损失；reference 包含初始 SFT adapter。旧 540 条只用于初始诊断和第一次更新，后续从新策略重新采样。

[框架入口与命令](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step03_grpo_framework/README.md) · [新题评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_cli0162_v1) · [训练产物](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1)

完整 train90 评分、outcome 对照和 dev57 已提供入口。本轮优先完成工程闭环，不预先宣称模型收益。后续正式预算仍按 [实验计划](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md) 冻结；长期扩展见 [研究设想](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/RESEARCH_IDEA.md)。
