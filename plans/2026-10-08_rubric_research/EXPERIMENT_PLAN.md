# 静态 rubric 双起点实验计划

更新：2026-10-09。本文集中管理后续实验安排，替代原实验目录中的 PROTOCOL.md 和 COMPARISON.md。最短的当前待办见 [README](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/README.md)；已执行事实见 [实验报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)。以下“计划产物”和训练参数约定均不代表已经执行。

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

现有 [judge.py](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/judge.py) 已有提示构建、调用、schema 校验和缓存；[common.py](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/common.py) 已有规则加载、reward 与 advantage 计算。**两份完整数据的批量评分、恢复及联合诊断入口尚未完成真实运行验证。** 不直接调用旧 `run.py all`，避免误入旧 pilot 或训练安排。

新入口的职责应限制在：校验已采轨迹 → 构建评分请求 → 保存判定 → 按完整六条组算奖励 → 输出检查表。读取冻结轨迹，不重新运行 AppWorld，不启动本地 Qwen 服务，不更新权重。

第二阶段使用独立的配置和来源清单，记录输入轨迹索引、规则、prompt、schema、judge 与脚本版本的校验值。第一阶段快照和结果不覆盖；若增加代码影响当前目录 fingerprint，以新阶段身份记录，不能把它伪装成采样时的源码。

### 3.2 小批量调用检查：24 条，不重新采样

在完整 train90 中按 `sha256("static-score-v1:20261009:" + task_id)` 排序取前两题，不读取成功标签选题。同两题 × 两个起点 × 六条 = 24 条，得到 504 个规则判定。

先跑一条确认请求及输出，再完成四个六条组。分支请求交错安排，初始低并发；检查完整历史是否被送入、few-shot 是否被误判成真实步骤、NA 是否符合适用条件。短小调试集不承担效果结论。

若检查通过，缓存直接计入全量评分，不再为同一输入重复取一个“更满意”的答案。若必须改变 prompt 或 schema，则统一新版本，原输出留档，两分支都按新版本评分。

### 3.3 全量规模与评分输入

总计 **1,080 条轨迹、180 个六条组、22,680 个规则判定**。正常情况下每条轨迹一次 judge 请求；24 条检查包含在这 1,080 条中。失败重试与额外审计调用另计。

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

例如保留项为 3 PASS、1 FAIL、2 NA，则 reward=5。所有原始判定保留，过滤只影响该组奖励，规则文件没有变化。这对应官方 `compute_group_discriminative_reward`、`_non_discriminative_indices` 及奖励聚合逻辑。[奖励源码](https://github.com/IBM/draco/blob/cfafd0f81f2c49aa36a4b25a2a7b6ac6e119f47b/training/src/verl_appworld/rubric_reward.py)

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

这些路径目前是产物约定，尚无评分结果。评分入口本身、运行配置和结果放 experiments；如何设计下一轮仍只写本 plans 目录。

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

本次整理未启动 judge、GRPO 或 dev，也没有改采样配置、模型、轨迹或来源快照。
