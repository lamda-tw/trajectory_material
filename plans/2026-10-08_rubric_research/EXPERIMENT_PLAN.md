# 静态 rubric 双起点实验计划

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

更新：2026-10-09。本文集中管理后续实验安排，替代原实验目录中的 PROTOCOL.md 和 COMPARISON.md。最短的当前待办见 [README](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/README.md)；已执行事实见 [实验报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)。以下“计划产物”和训练参数约定均不代表已经执行。

## 2026-10-09 最新执行优先级

用户再次确认优先做通 DRACO 静态评分、reward、GRPO 框架。新增 step03_grpo_framework：首批固定为原新题顺序第一题 afc0fce_1 的完整六条；一次工程更新、一个 PPO epoch；lr=5e-5、KL=0.01、clip=0.2，损失按轨迹内生成 token 平均后再按轨迹平均。零优势组保留并应用 KL，不按奖励方差挑组。此预算不替代正式 train90 对照预算。

policy 和 reference 分别加载，reference 固定为初始 SFT 模型。首次允许复用对应权重的初始轨迹，后续从新 checkpoint 重新采样。用户本次明确允许临时 GPU 1，覆盖下文历史 GPU 0 限制。真实 8B 前向预检及一次实际 GRPO 更新已通过；18 条新题评分完成。详细指标见 README 和实际产物，正式 dev57 尚未执行。

Codex 0.162.0 使用新评分目录 draco_baseline_newtasks_cli0162_v1，保留最早有效响应及全部日志。仅适配已成功恢复的传输事件，不改变规则、prompt 或语义校验。下文“无训练入口”“401 待恢复”“必须全量评分后才接训练”是历史状态，以本节为准。完整评分和 dev57 设计保留，先接通工程链路。

## 本轮执行范围与完成状态

2026-10-09 用户指定先在 LoRA 实验目录完成静态评分及校准重测。样本始终是两个固定 train 题 `e7a10f8_3`、`29caf6f_1`，每题六条，共 12 条；raw 分支未调用 judge。

v2 原始 smoke 为 252 项、PASS 127 / FAIL 86 / NA 39，工程链路通过但存在判分问题。v3 校准重测同批 12 条，官方 21 条规则、模型、轨迹与 reward 公式不变；独立 wrapper 明确具体条款优先和真实执行边界，R19 的 NA 会被校验拒绝而非改写分数。12 次新请求全部首次成功，得到 PASS 137 / FAIL 78 / NA 37，与 v2 相比 13 项变化。

原三处 R19 无错误却判 NA、一处未发生打印却判泄密，全部纠正。但是全部变化项的复核发现：短信 00 的 R10 仍把第 10 步异常之后未执行的分页当成已执行证据。固定 30 项配对复核有 27 项得到支持、3 项边界问题；另复核全部 13 项变化，两批合计 42 个不同判定。**工程验收通过，语义验收未通过，未进入 540 条评分或训练。**

结果见 [v3 smoke 报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/SMOKE_REPORT.md)；[主实验报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)已经包含真实 Spotify 题的 21×6 判定矩阵、过滤集合、逐条计数、reward 代入和 advantage 计算。这是助手的证据复核，不是独立人工金标。两版结果均保留，未手改原分数。

本批两组均为 outcome 混合组，不能替代 23 个全失败组的诊断。校准提示已经参考了本批错误，因此同批重测不能证明 judge 在新任务上的可靠性。原双起点 24 条 smoke / 1,080 条评分保留为后续配对方案，不代表已执行。

### 当前决定：回到 DRACO 静态基线，停止两题上的提示调优

用户指出：只根据两个题修改面向 train90 的通用提示，可能导致过度适配；当前应该以复现 DRACO 为主。采用这一方向。v3 的已知误判与复核结论保留为历史事实，不继续把每一处争议变成新的硬性规则。

**当前评分采用与 v2 相同的基线配置。** 官方 21 条规则的 title / description / evaluator_instruction 原文不变；官方 score_rubrics.txt 中的证据、评估、PASS/FAIL/NA 与解释要求保留。只替换本地不适用的 XML/完成后继续交互说明，并适配 JSON 顶层对象和 few-shot/实际轨迹边界；不会重新定义规则触发条件、覆盖范围或 NA 语义。

明确撤出主线的 v3 机制：额外的规则优先级说明、针对秘密打印/候选写入/live data 等规则的解释段落，以及恢复项禁止 NA 的语义校验。只保留原始结构校验：21 项齐全、顺序和标题一致、取值为 -1/0/+1、依据非空。对于官方通用 NA 提示与具体恢复条款的张力，保留原文并记录 judge 的真实选择，不在本地改写答案。

下一步执行已冻结：

1. 按相同 SHA256 顺序取原两题后的 **三个新题 × 六条 = 18 条**；任务为 afc0fce_1、e85d92a_3、7d7fbf6_3。不按应用、结果或新评分重新挑选，不重采轨迹，不使用 dev。
2. 固定评分器后一次完成评分；仅技术失败按既有最多两次策略重试，不因语义上不满意而重抽。评分前按 hash 在每题固定 10 个轨迹—规则对，共 30 项做证据复核。
3. 工程检查包括来源、请求完整性、JSON、完整六条组和 reward 重算。语义误判分成明确证据错误与规则歧义，描述影响范围，不把复核意见写回原始 verdict。
4. 不用更高 reward、更接近官方 success 或旧题问题全部消失来选提示。新题也不能再变成下一轮 prompt 修补的样本。少量 judge 噪声不是自动停下所有实验的理由；若出现跨题的明显协议误读或证据泄露，再讨论一般性的实现适配。
5. 小样本记录完成后安排 LoRA 540 条评分和训练接入。主线只复用与当前基线请求配置相同的有效缓存；**v3 校准分数不能混入**。后续真正关心的是与 outcome 奖励相比，静态 rubric GRPO 在完整 dev57 是否有收益。

新题入口为 [baseline_newtasks.py](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step02_static_scores/baseline_newtasks.py)，运行目录为 [draco_baseline_newtasks_v1](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1)。新题评分已尝试启动，但本执行环境返回 401 / 缺少认证信息，进程已停止，有效评分 0/18。用户确认其终端可正常运行 Codex，因此正在核对主机、入口和认证上下文差异，不把默认 CLI 检查外推为整个服务器未登录。恢复入口 resume_baseline_newtasks.py 已完成离线检查；尚未开始全量评分、GRPO 或新 dev。这个检查不是独立人工金标评估，也没有对比两个提示在同一批新题上的因果效果。

## 1. 我们在对齐 DRACO 的哪一部分

当前采用 **static：固定规则、轨迹级评分、普通轨迹优势**。官方另有 static + credit、dynamic 和 dynamic + credit 等设置；动态规则和步骤归因各自是额外机制。因此这里是 Qwen3-8B 上的静态流程基线，不声称复现完整 DRACO 或原论文数值。[官方设置说明](https://github.com/IBM/draco/blob/cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b/README.md)

代码来源固定为 `cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b`。已复制的 21 条规则、原评分提示、奖励源码与许可文件都有 [来源及 SHA256](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/assets/draco/provenance.json)。

需要如实披露的差异：

| 项目 | 官方实现 | 本地安排 |
| --- | --- | --- |
| 模型 | 主设置 Qwen3.6-27B | Qwen3-8B，另加现有 SFT LoRA 起点 |
| 训练栈 | verl | 已有 PyTorch / Transformers / PEFT 原型，续训仍待接入 |
| 训练 LoRA | rank 16、alpha 32 | 拟统一 rank 8、alpha 16，以匹配现有 SFT adapter |
| 资源与批次 | 8 张 H100；每批 16 题、每题 6 条 | GPU 0 分时采样和训练；本地训练预算另行冻结 |
| 交互协议 | 官方 agent scaffold | 现有 Python fence / ReAct runner，完成 API 后自动结束 |
| judge | 官方配置的外部模型 | 本地已准备的 Codex judge；版本和调用时间记录在案 |

官方训练每批只跑一个 PPO epoch；本地也以更新后重新采样为原则。上述规模、LoRA 与栈的差异需要进入实际训练报告。[官方超参数](https://github.com/IBM/draco/blob/cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b/training/docs/HYPERPARAMETERS.md)

## 2. 已有输入与这次要回答的问题

| 训练内诊断 | 原始 Qwen3-8B | 现有 SFT LoRA |
| --- | --- | --- |
| 完整轨迹 / 完整组 | 540 / 90 | 540 / 90 |
| 官方终态成功 | 39/540 | 186/540 |
| 六次全失败 | 70 题 | 23 题 |
| 成功/失败混合 | 20 题 | 63 题 |
| 六次全成功 | 0 题 | 4 题 |
| 0/1 奖励有差异的组 | 20/90 | 63/90 |

来源：[raw 验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/collection_validation.json)、[LoRA 验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/collection_validation.json)。两份数据均为完整 train90、每题六次，任务与 seed 配对。失败、无代码和预算耗尽样本全部保留。

第一问：**最终结果相同的六条轨迹，是否仍有可信的规则表现差异？** 第二问留给训练：**这些差异能否带来完整 dev 上的自主执行进步？** 有方差只说明可以算优势，不说明判断正确或学习有效。

LoRA 来自 [既有 train90 / epoch5 训练](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter)，使用过 90 条 Codex 成功轨迹、1170 个决策样本。冻结副本位于 [initial_adapter](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/initial_adapter)，权重 SHA256 为 `c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`。

因此 LoRA 这次采样属于训练内诊断；两个起点的绝对差距不是 rubric 收益，也不是相同历史监督预算下的比较。历史 dev 的 23/57 仅作背景，本次重新统一测基线。

## 3. 下一步：固定规则评分，先做通再做全

### 3.1 先复用已有实现，补一个独立的第二步入口

现有 [judge.py](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/judge.py) 已有提示构建、调用、schema 校验和缓存；[common.py](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/common.py) 已有规则加载、reward 与 advantage 计算。LoRA 的 [12 条 smoke 入口](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step02_static_scores/smoke_v2.py) 已完成真实运行和技术验收；阶段通过 judge_compat.py 接纳一条已知的 turn 前 CLI 诊断，仍拒绝工具调用和其他错误。校准入口 [smoke_v3.py](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step02_static_scores/smoke_v3.py) 也已完成同批真实重测，但仍有执行依据误读，当时语义验收未通过；**当前已停止将 v3 作为基线，改用仅含原协议适配的新题入口。两份完整数据批量评分尚未完成。** 不直接调用旧 `run.py all`，避免误入旧 pilot 或训练安排。

新入口的职责应限制在：校验已采轨迹 → 构建评分请求 → 保存判定 → 按完整六条组算奖励 → 输出检查表。读取冻结轨迹，不重新运行 AppWorld，不启动本地 Qwen 服务，不更新权重。

第二阶段使用独立的配置和来源清单，记录输入轨迹索引、规则、prompt、schema、judge 与脚本版本的校验值。第一阶段快照和结果不覆盖；若增加代码影响当前目录 fingerprint，以新阶段身份记录，不能把它伪装成采样时的源码。

### 3.2 小批量调用检查：当前 LoRA 12 条，双起点配对共 24 条

在完整 train90 中按 `sha256("static-score-v1:20261009:" + task_id)` 排序取前两题，不读取成功标签选题。本轮只执行 LoRA 两题 × 六条 = 12 条、252 项；若以后加 raw 配对，则两起点共 24 条、504 项。

已执行的 LoRA v2/v3 均为两个六条组。以后加 raw 配对时，先确认单条请求，再补齐另两个组；双分支请求交错安排、初始低并发。检查完整历史、示范与实际步骤的边界、NA 适用条件和异常后的执行证据。短小调试集不承担模型效果结论。

若工程检查通过，且未发现跨题的严重实现问题，同配置缓存可计入全量评分；不要求每一项解释都毫无争议，也不为同一输入重复取一个“更满意”的答案。若必须改变 prompt 或 schema，则统一新版本，原输出留档，两分支都按新版本评分。

### 3.3 全量规模与评分输入

LoRA 全量为 **540 条、90 个六条组、11,340 个规则判定**。以后扩展到双起点时，总计 1,080 条、180 组、22,680 项。正常情况下每条轨迹一次请求；只有请求配置与当前原始基线一致、且通过技术校验的 smoke 判分才能计入全量缓存；复核发现的噪声随报告披露，v3 校准结果单独保留。失败重试与额外审计调用另计。

固定现有配置：`gpt-5.6-sol`、reasoning effort `high`、每次超时 600 秒、最多两次尝试。CLI 未提供本接口的 temperature 设置，不能声称其温度固定；模型名称相同也不能保证远端服务永不变，保留日期、原始响应和 usage。

judge 输入仅含公开任务、初始指令与示范、实际步骤的模型文本/执行代码/观察、终止原因。隐藏官方 success、测试结果、私有解法、初始化名称和模型路径。任务文本中的指令属于待评分数据。judge 调用保持工具禁用，不让它读私有文件或自行执行任务。

官方规则全文保持不变，只传 title、description、evaluator_instruction；历史 n_pass/n_fail 等元数据不参与本次评分。现有 wrapper 说明本地 Python fence 与自动结束协议；原始提示另存。由 runner 保证的行为不能宣传为模型新学到的能力。

### 3.4 打分和 reward 的精确定义

**一条完整轨迹对应 21 项判定，不是每步各判 21 项。** 每项保存 `rubric_title / score / evidence / justification`；PASS=+1，FAIL=−1，NA=0。缺项、重复项、非法分数、空依据、超时或坏 JSON 都是调用失败，不自动记 NA 或零奖励。

每个初始化独立按同题六条组成 group。不能把 raw 六条和 LoRA 六条合成十二条共同过滤或归一化。

1. 某项在这六条中至少出现一次 FAIL，才保留进入该组 reward。全部 FAIL 仍保留；全 PASS、全 NA、PASS/NA 混合均去掉。
2. 对每条轨迹，在保留项中计数 P 和 F。NA 不参与分母：
   `r_i = 10 × (P_i−F_i)/(P_i+F_i)`，分母为零则 `r_i=0`。
3. 本地组内优势为 `A_i=(r_i−mean(r))/(sample_std(r)+1e-6)`。六条 reward 相等时 A 全零。
4. rubric 分支只使用该奖励。官方 0/1 成功标签仅用于独立诊断；outcome 对照分支才将它作为训练奖励。

例如保留项为 3 PASS、1 FAIL、2 NA，则 reward=5。实际 Spotify 00 的保留项为 10 PASS、1 FAIL、1 NA，reward=90/11；全部六条的完整推导见 [真实算例](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/REWARD_WORKED_EXAMPLE.md)。所有原始判定保留，过滤只影响该组奖励，规则文件没有变化。这对应官方 `compute_group_discriminative_reward`、`_non_discriminative_indices` 及奖励聚合逻辑。[奖励源码](https://github.com/IBM/draco/blob/cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b/training/src/verl_appworld/rubric_reward.py)

静态基线将同一个轨迹优势赋给该轨迹的模型生成 token。以后若加 credit，再单独定位负责的步骤；它不等于逐步重判整套规则。[credit 说明](https://github.com/IBM/draco/blob/cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b/training/docs/CREDIT.md)

### 3.5 评分结束后必须能回答什么

| 检查 | 具体看什么 |
| --- | --- |
| 完整性 | 1,080 个有效评分、每个恰好 21 项；180 个完整六条组；来源及缓存一致 |
| 信号覆盖 | 各分支 outcome/rubric 的零优势组数、reward 标准差、保留规则数、NA 比例 |
| 额外信号 | 全失败、混合、全成功三类中，分别多少组获得非零 rubric 优势 |
| 判分可靠性 | 证据能否在实际轨迹找到；是否误读示范、完成协议、错误恢复或 NA |
| 目标一致性 | 高 rubric / 官方失败，以及低 rubric / 官方成功的案例和原因 |
| 成本 | 调用、重试、耗时、输入输出 token；不把 22,680 项当成 22,680 次调用 |

按固定 seed 在两分支各抽查 30 个规则判定，尽量覆盖 PASS/FAIL/NA，各保留证据定位和复核备注；某类不足就全部检查并注明。再看每分支 rubric 与官方结果分歧最大的五条轨迹。选择与复核方式随报告公开，助手的证据复核不能写成独立人工金标。

对于全失败但 reward 有差异的组，检查高分是否仅来自更早停止、较多 NA 或分母缩小。真实的过程改进也可能尚未导致终态成功；不要简单把所有不一致都视为 judge 错误。

若评分有系统性的协议误判，先修正适配、两边统一重评。若评分可信却几乎没有组内差异，也如实报告，再决定下一项小改动；不靠挑组、挑分制造积极结果。

### 3.6 第二步计划产物

各分支拟写入各自 `runs/step02_static_scores/`：阶段清单、逐轨迹判分原文与有效结果、逐组六条 reward/advantage、逐规则统计、抽查记录、调用成本与恢复状态。两分支汇总写入 LoRA 实验的同阶段结果目录，并追加已有实验报告。

LoRA 原始 smoke 位于 runs/step02_static_scores/smoke_v2；校准重测位于 smoke_v3_calibrated；第一版启动提示误判与原文保留在 smoke_v1。v3 有独立来源清单、原始响应、证据复核和 reward 计算详解，现只作历史校准记录。当前主线的新题静态基线目录为 draco_baseline_newtasks_v1。全量产物仍待执行。评分入口本身、运行配置和结果放 experiments；如何设计下一轮仍只写本 plans 目录。

## 4. 评分之后，怎样接 GRPO

### 4.1 先补齐实际训练条件

旧原型默认新建 rank16 adapter，以禁用 adapter 的基座作为 reference；不能直接套用 LoRA 续训。双起点约定如下：

| 项目 | Raw 分支 | SFT LoRA 分支 |
| --- | --- | --- |
| 初始 policy | 基座 + 新建零增量 rank8 / alpha16 adapter | 基座 + 冻结副本加载出的现有 rank8 / alpha16 adapter |
| KL reference | 冻结原始基座 | 冻结的初始 SFT policy，包含原 adapter |
| optimizer | 本轮新建 | 本轮新建，不恢复历史 SFT optimizer |
| 训练数据 | 本分支当前 policy 新采样 | 本分支当前 policy 新采样 |
| 输出 | 独立新 checkpoint | 独立新 checkpoint，不覆盖初始 adapter |

七个投影模块、dropout=0、可训练参数规模、优化器与新增训练预算对齐。LoRA reference 和 policy 参数不能共享可变存储；reference 不进 optimizer。若采用多 adapter，前向与 gradient checkpointing 重算必须始终选对 adapter。

工程验证包括：reference 不变、policy 更新、仅生成 token 计损失、保存重载一致、旧策略 logprob 与训练 forward 对齐。真实 8B 首次更新还需检查显存、ratio、clip fraction、KL 与梯度；当前采样验收不等于已验证训练。

候选原型的 lr=5e-5、KL=0.01、clip=0.2、每批一个 PPO epoch 可以作为实现检查起点。实际批量、更新数、归一化方式和总预算需在正式运行前记录到本文及独立运行配置。现有 config 的 updates=10 / groups_per_update=2 属于旧 train8 原型，不能自动成为本次完整 train90 实验的协议。

继续只用 GPU 0；生成服务退出并释放显存后再训练。GPU 1 不纳入资源安排。

### 4.2 现有 540 条怎么用，避免变成反复训练旧数据

这两份数据首先是完整的初始策略评分诊断。完成训练接入后，若权重、prompt、token、旧 logprob 和任务选择都对齐，可以将预先指定的一批用于该分支的第一次更新。

**不能将现有 540 条切成许多批，在策略不断更新后仍称为每批 on-policy 采样。** 若首批只用两题，其他初始轨迹继续用于诊断，不默认作为后续更新数据。下一轮从新策略采新的六条组，再评分再更新；更换 trainer 或策略导致概率不匹配时，重新采首批。

每个阶段保留采样 policy ID、父 checkpoint、真实 old logprob 与批次 hash。raw 与 LoRA 不混数据。任务覆盖按完整 train90 排程，不因某组没有优势而只保留“容易训练”的组；是否跳过整个零优势批次、KL 的处理及实际更新次数需事先固定并记录。

### 4.3 对照和预算怎么定

先跑两个初始化各自未更新的完整 dev57。训练可行性接通后，在看训练后 dev 成绩之前冻结共同的 train 任务顺序、采样预算、更新数与最终评估点。每个正式报告的训练条件都跑完整 dev57。

| 起点 | 未更新 | outcome GRPO | static rubric GRPO |
| --- | --- | --- | --- |
| Raw | R0 | R-outcome | R-rubric |
| SFT LoRA | L0 | L-outcome | L-rubric |

最小链路可以先拿到 R0/R-rubric、L0/L-rubric 四个结果；这仅检验更新是否有收益。要讨论“rubric 相比最终结果奖励的价值”，需补齐两个 outcome 对照，形成六个评测条件。

重点报告 R-rubric−R0、L-rubric−L0，以及各自 rubric 对 outcome 的差异。L-rubric−R-rubric 只代表整个系统的差异。匹配新增任务数、每题采样数、更新数及解码预算，同时单独报告实际 token、judge 成本和 GPU 时间；不能把同 rollout 数写成同总算力。

## 5. 所有模型统一完整 dev57

完整官方 57 题；temperature=0、seed=100、不开 thinking；同 prompt、parser、50 步上限、32000 上下文、单步最多 3000 token。初始和训练后模型从完整任务起点自主执行，不提供 rubric 提醒、错误位置或修复动作。

主指标为官方 TGC，辅以 SGC 和逐题变化，保存精确分子/分母。基础设施故障恢复后补齐，不能当模型失败填零。预先指定最终 checkpoint，不分别挑各分支最高的 dev 点。

训练、judge 诊断与修复样本只来自 train。dev 用于开发比较，不回灌其轨迹、答案或修复；当前不使用 test。反复使用 dev 选型时，成绩按开发验证报告，不宣称独立测试结论。

## 6. 后续研究从这里衔接

若静态奖励与训练成立，再按观察到的瓶颈选一个机制：步骤 credit、规则提示下的学生自修复、去提示 SFT，之后才考虑 OPD 与多轮调度。完整故事见 [RESEARCH_IDEA](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/RESEARCH_IDEA.md)。

单独的静态 DRACO 基线、两个初始化比较、或增加一个循环都不足以成为新方法。拟研究的是固定标准下“能被提醒修好”怎样转化为“无提示也能做好”，需要额外对照与跨任务证据。

## 7. 文件与历史记录的边界

本目录管理当前待办、实验设计、后续预算和研究路线。两个实验目录保存运行代码、已落地配置、日志、结果、报告以及必要的来源记录；实验 README 只说明完成状态与产物入口。

原 PROTOCOL.md 中 train8、459 条总预算、10 次更新、GPU 1 训练等安排已废弃。原 COMPARISON.md 的有效约定已并入本文。实验目录的历史 source_snapshot 和第三方 assets 文档属于不可变来源记录，保留原样，不再作为当前待办入口。

2026-10-09 已在用户授权下完成 LoRA 12 条 judge smoke 及同批校准重测，没有执行全量评分、GRPO 或新 dev；原采样配置、模型、轨迹和来源快照均未改。
