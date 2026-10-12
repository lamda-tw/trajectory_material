# 静态 Rubric GRPO 实验报告

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

## 本次已完成：DRACO 静态 GRPO 工程闭环

2026-10-09：新题评分 **18/18**、378 项判定、3 个完整组；GPU 1 完成 Qwen3-8B SFT LoRA **一次真实更新**，policy 权重发生变化、初始 SFT reference 保持冻结、保存重载 logprob 检查通过。未运行全量 540 评分或 dev57，不据此宣称效果提升。

[本次完整工程报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1/FRAMEWORK_REPORT.md) · [框架入口](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step03_grpo_framework/README.md) · [训练 checkpoint](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step03_grpo_framework_v1/rubric/update_001/checkpoint)

本报告持续追加实验步骤；时间使用 Asia/Shanghai。

## 当前完成状态

原始 Qwen3-8B 与 SFT LoRA 各完成 train90 × 6，共 1,080 条轨迹；LoRA 的原始 12 条 smoke 与同批校准重测已完成。当前按用户要求回到官方静态基线，只保留必要协议适配，v3 校准结果作为历史记录保留。

另三个新 train 题的 18 条评分输入已经冻结，但启动遇到本执行环境的独立 Codex CLI 认证错误，已停止，尚无新分数。详见 [当前启动记录](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/SMOKE_REPORT.md)。本系列尚无 GRPO 更新或新 dev 评测结果。

本报告只记录实际执行；总体安排见 [当前待办](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/README.md) 和 [实验计划](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md)。以下历史记录按发生顺序保留。

## 第一步：完整训练集采样

- 模型：/root/autodl-tmp/models/Qwen3-8B；不加载任何 LoRA、不更新权重。
- 完整官方 train.txt 的 90 题；每题 6 条，分别重置 AppWorld，使用不同且固定的随机种子。
- temperature=1，top_p=1，top_k=-1，repetition_penalty=1，enable_thinking=false。
- 最多 50 步；上下文 32000，每步最多生成 3000 token；上下文耗尽就结束，不裁剪历史。
- 保存原始响应、执行代码、环境反馈、prompt/response token IDs、旧策略 logprobs。
- 随轨迹保存官方终态测试，仅作采样诊断；不是 rubric 评分或 dev 结果，标签不提供给策略/judge。
- GPU 0 运行 vLLM，首条顺序校验后最多 6 个隔离 AppWorld 进程并发；GPU 1 不使用。
- 仅恢复身份、配置、策略一致的完整轨迹；基础设施故障不当成模型失败填零。

<!-- STEP01_PROGRESS_START -->
更新时间：2026-10-08T21:06:36+08:00。状态：**已完成**。

| 项目 | 当前值 |
| --- | --- |
| 完整轨迹 | 540 / 540 |
| 已收齐 6 条的任务 | 90 / 90 |
| 官方终态成功的轨迹 | 39 / 540 |
| 完整组中至少一条成功的任务 | 20 / 90 |
| 模型生成步骤 | 11254 |
| 生成 token | 1366894 |
| Codex 调用 / GRPO 更新 / dev 轨迹 | 0 / 0 / 0 |

终止原因计数：{"completion_api": 312, "no_python_code": 111, "step_limit": 97, "context_limit": 20}。

产物：[逐任务统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/task_summary.csv)、[轨迹索引与校验值](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/trajectory_index.json)、[进度 JSON](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/progress.json)。

**上述成功比例来自 train 随机采样，只用于数据诊断，不能当成 dev 成绩。**
<!-- STEP01_PROGRESS_END -->

## 运行记录

- 2026-10-08T19:34:24+08:00：按用户要求启动第一步。不调用 Codex、不做 GRPO、不跑 dev。

- 2026-10-08T21:06:36+08:00：第一步完成，540 条轨迹、90 个完整组。未执行规则评分或 GRPO。

## 第一步收尾结果

采样开始于 2026-10-08T19:34:37+08:00，结束于 2026-10-08T21:06:36+08:00，本次连续运行耗时 **92.0 分钟**。采样服务已正常退出，两张 GPU 显存均已释放到启动前水平。

**90 题 × 6 条 = 540 条，已全部收齐并通过数据验收。** 共 11,254 个模型生成步骤，生成 1,366,894 个 token；平均每条 20.84 步，中位数 14 步。累计 prompt token 为 98,035,632，其中包含重复历史与命中的前缀缓存，不能把它当成独立文本量或实际计算量。

官方终态测试通过 **39/540（7.22%）**；**20/90（22.22%）** 的题在六次采样中至少成功一次。这些是 **train 随机采样诊断**，不代表 dev 的贪心解码成绩。

| 一道题六次中的成功次数 | 题数 |
| --- | --- |
| 0 | 70 |
| 1 | 9 |
| 2 | 7 |
| 3 | 1 |
| 4 | 2 |
| 5 | 1 |
| 6 | 0 |

若后续使用官方 0/1 结果奖励，当前仅 **20/90** 个组存在组内差异；其余 **70/90** 个组没有相对优势信号。静态 rubric 能否提供有用的额外差异，必须等第二步实际评分后判断。

| 轨迹终止原因 | 数量 |
| --- | --- |
| 完成接口触发结束 | 312 |
| 模型未给出可执行 Python 块 | 111 |
| 达到 50 步上限 | 97 |
| 达到上下文预算 | 20 |

完成接口触发结束共有 312 条，不能将其视为 312 条成功轨迹；以官方终态测试的 39 条通过为准。全部轨迹均保留，没有筛掉失败、无代码输出或预算耗尽的样本。

环境输出以 “Execution failed” 开头的步骤共 5,073 个。这只是执行日志统计，尚未做 rubric 判定或“能力”分类，也不能直接当作独立错误根因数。

### 数据验收

- 90 个任务均覆盖完整六条，任务与 seed 配对无重复，来源均为同一个冻结的原始 Qwen3-8B，没有加载旧 LoRA。
- 全部 540 条轨迹的 SHA256 与索引一致；全部 response token 都能精确还原原始响应。
- 全部 11,254 步的 prompt token 都能由保存的对话历史精确重建；旧策略 logprob 与 response token 一一对齐、数值有限。
- 同一题六条轨迹的初始 prompt 一致；步数和上下文预算检查通过。
- 33 个阶段快照文件校验通过；保存了采样时的源码、配置、任务清单、静态规则与模型元数据，便于后续版本追溯。
- 本步没有基础设施失败或自动重试，没有 Codex 评分调用、优化器更新或 dev rollout。

验收明细：[collection_validation.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/collection_validation.json)；阶段快照：[source_snapshot_manifest.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/source_snapshot_manifest.json)；长度与耗时统计：[descriptive_statistics.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/descriptive_statistics.json)。

- 2026-10-08T21:14:56+08:00：完整数据验收通过，第一步正式结束。本报告后续直接追加第二步及后续实验结果。

## 2026-10-08：第二起点的离线准备记录

2026-10-08 启动前，按用户要求完成 LoRA 起点的离线准备；该阶段尚未执行采样。原始 540 条轨迹及其冻结采样快照、索引保持不变。之后的启动、故障与恢复记录见下文。

指定 adapter 为 train90 / epoch5 的最终产物，rank=8、alpha=16，共 21,823,488 个 LoRA 参数。已复制冻结副本并验证权重 SHA256 为 c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938，与原训练报告及历史 dev 评测记录一致。

历史 [dev57 summary](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/summary.json) 记录 23/57 成功（TGC 40.4%，SGC 21.1%）。这是选择第二起点的依据，不是本次新评测结果；本系列尚无统一协议下的新 dev57 基线。

### 当时完成的准备

- 独立目录：[2026-10-08_static_rubric_grpo_lora_init](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/README.md)。
- 采样入口配置为 GPU 0、端口 8129、最多 6 路并发，任务清单为 train90 × 6。
- 全部 540 个任务 / sample / seed 与 raw 分支配对；prompt、parser、采样参数和执行预算一致。
- 单独冻结 adapter、静态规则与 judge 接口；准备首条及全量 token 验收、断点恢复、采样统计和报告追加。
- LoRA 新轨迹、新 logprob、新日志单独存放；不复用 raw 轨迹充作 LoRA 策略数据。
- 离线验证通过：504 个 adapter 张量结构正确、12 项回归测试通过、原始 540 条轨迹哈希全部一致；当时新分支已有 540 个采样作业清单，实际轨迹为 0。
- 离线准备阶段未启动 vLLM、未调用 Codex、未做优化器更新、未执行 dev；服务加载的真实验证发生在随后采样阶段。

该 adapter 已见过同一 train90 的 Codex 示范，因此训练内采样差值不能解释为本轮 rubric 收益。当时仅完成采样入口和离线检查，尚未实现 LoRA GRPO 续训入口；本报告不将旧原型配置视为已执行训练。

<!-- LORA_STEP01_PROGRESS_START -->
更新时间：2026-10-09T10:11:02+08:00。状态：**已完成**。

| 项目 | 当前值 |
| --- | --- |
| 完整轨迹 | 540 / 540 |
| 已收齐 6 条的任务 | 90 / 90 |
| 官方终态成功的轨迹 | 186 / 540 |
| 完整组中至少一条成功的任务 | 67 / 90 |
| 模型生成步骤 | 9886 |
| 生成 token | 1785724 |
| Codex 调用 / GRPO 更新 / dev 轨迹 | 0 / 0 / 0 |

终止原因计数：{"completion_api": 472, "context_limit": 45, "step_limit": 19, "no_python_code": 4}。

产物：[逐任务统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/task_summary.csv)、[轨迹索引与校验值](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectory_index.json)、[进度 JSON](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/progress.json)。

**上述成功比例来自 train 随机采样，只用于数据诊断，不能当成 dev 成绩。**
<!-- LORA_STEP01_PROGRESS_END -->

- 2026-10-08T21:36:35+08:00：LoRA 对照离线准备检查通过，未启动实验。

- 2026-10-08T21:43:37+08:00：用户授权无人值守启动 LoRA 采样；仅 GPU 0。基础设施异常最多恢复 3 次，已完成且身份一致的轨迹保留。

- 2026-10-08T23:44:19+08:00：LoRA 采样尝试 1 返回 1；记录日志，不把基础设施异常作为模型失败。

- 2026-10-09T00:18:50+08:00：LoRA 采样尝试 2 返回 1；记录日志，不把基础设施异常作为模型失败。

- 2026-10-09T00:20:22+08:00：LoRA 采样尝试 3 返回 1；记录日志，不把基础设施异常作为模型失败。

- 2026-10-09T00:20:22+08:00：无人值守采样未完成：RuntimeError: Three collection attempts failed; see runs/unattended.log and per-job logs.。已完成数据保留；详情见 /root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/unattended_status.json。

## 2026-10-09：恢复中断采样与报告迁移

报告已从工作区根目录移入本实验目录；当前入口只向 experiments 内写入。昨夜完成 342/540 条后，AppWorld 在将含 Python Ellipsis（...）的 API 参数写入日志时抛出序列化错误，三次尝试后停止。

本次只补齐剩余 198 条：模型、adapter、采样参数、任务和 seed 均不变。修复仅为 RequestTracker.save 增加 Ellipsis 的显式日志编码，不修改实际请求、模型动作、环境错误反馈或终态评价。3 项序列化回归检查、真实 AppWorld 故障复现和原有 12 项离线检查均通过。

342 条完整轨迹已逐文件核对 SHA256 并原样保留。原始 collection fingerprint 继续标识冻结任务计划；新轨迹另存 runtime fingerprint 与维护清单校验值，明确区分修复前后代码版本。旧清单、源码、未完成轨迹和失败状态保存在 recovery/2026-10-09/before/。

恢复版本：0084e5d4cca518ee3fb956a5c6e7cf93d0c12111e5928cf687f1380e12606052。本次继续使用 GPU 0，不运行评分、GRPO 或 dev。

- 2026-10-09T09:16:17+08:00：用户授权无人值守启动 LoRA 采样；仅 GPU 0。基础设施异常最多恢复 3 次，已完成且身份一致的轨迹保留。

- 2026-10-09T10:14:22+08:00：LoRA 对照分支第一步完成，540 条轨迹、90 个完整组。未执行规则评分或 GRPO。

## 无人值守 LoRA 采样完成

开始：2026-10-09T09:16:17+08:00；结束：2026-10-09T10:14:22+08:00。共 1 次运行尝试，总耗时 58.1 分钟。

| train 随机采样诊断 | 原始 Qwen3-8B | 现有 SFT LoRA |
| --- | --- | --- |
| 完整轨迹 | 540 | 540 |
| 官方终态成功 | 39/540 | 186/540 |
| 六次全失败的题 | 70 | 23 |
| 成功/失败混合的题 | 20 | 63 |
| 六次全成功的题 | 0 | 4 |
| 总生成步骤 | 11254 | 9886 |
| 生成 token | 1366894 | 1785724 |

这张表只说明两个初始化在 train 上的采样情况。LoRA 已用 train90 示范训练过，不能将差值解释为本轮 rubric 收益，也不是 dev 结果。

全部 LoRA 轨迹的校验值、response token 解码、prompt 重建、旧策略 logprob 对齐及初始 prompt 配对均通过。采样服务已退出；本轮没有 rubric 评分、GRPO 权重更新或 dev 评测。

产物：[LoRA 轨迹索引](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectory_index.json)、[完整验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/collection_validation.json)、[两分支采样统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/collection_comparison.json)。

## 2026-10-09 恢复完成：最终验收

最终 **540/540 条、90/90 个六条组**。官方 train 终态成功 **186/540（34.44%）**，67/90 题至少一次成功。这是训练内随机采样诊断，不是 dev 成绩，也没有进行 rubric 评分或 GRPO 更新。

原有 **342 条完整轨迹 SHA256 全部保持一致**，新增 **198 条**均保存恢复版本信息。全部 540 条完成 token 重建、真实旧策略 logprob 对齐和数据完整性验收。有 1 条新轨迹实际触发了 Ellipsis 日志兼容编码；模型的原动作、真实错误反馈与官方评价均保留。

全失败组 23 个，混合成功/失败组 63 个，全成功组 4 个；对应 0/1 结果奖励的有效组仅为混合组。rubric 是否提供更多可靠差异，仍待实际评分。

本次恢复耗时 58.1 分钟；含昨夜失败尝试的累计运行时间约 214.8 分钟，不含中间无人运行的间隔。

详细统计：[final_diagnostics.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/recovery/2026-10-09/final_diagnostics.json)。报告现仅位于本实验目录，工作区根目录原报告已移除。

<!-- STEP02_SMOKE_STATUS_START -->
## 2026-10-09：LoRA 静态 rubric smoke 完成

只对固定两题的 12 条已有轨迹评分，共 252 项：PASS 127、FAIL 86、NA 39。两组六条均有非零 rubric 优势，也均为 outcome 混合组；不能由本次证明全失败组能受益。没有重采样、GRPO 或 dev。

用户明确授权后，由服务器的独立 Codex CLI 调用实验配置的 gpt-5.6-sol/high。实际 13 次请求，包含首条因本地启动提示校验误判产生的一次多余重试。已修复阶段兼容逻辑，采用第一次完整返回；原 judge.py、规则和采样数据未改。

工程验收通过，证据质量仍需校准：三条无错误轨迹被违反原规则地判为恢复项 NA；一项将未执行的打印判为秘密泄露；额外重试的一条规则判定有分歧。30 项固定抽查与扩大核查均已留档，未手改原始分数，也未将它们用于训练。

完整结果及成本：[SMOKE_REPORT.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v2/SMOKE_REPORT.md)。后续规划统一在 plans。
<!-- STEP02_SMOKE_STATUS_END -->

<!-- STEP02_CALIBRATED_SMOKE_START -->
## 2026-10-09：LoRA 校准重测 smoke 与 reward 计算明细

完成时间：2026-10-09T14:23:01+08:00。评分运行于 2026-10-09 14:11–14:17（Asia/Shanghai）。

**同一批 12 条已校准重测，原先四处明确问题得到纠正；工程链路通过，语义验收仍未通过。** 复核新结果又发现一处把未执行分页当作完成分页的依据错误。以下 reward 是完整保留的真实 judge 输出经程序计算所得，不能把“算得出来”当作“已适合训练”。本次未扩大至 540 条、未运行 GRPO、未新增 dev 评测。

## 这次改了什么，什么没有改

沿用 LoRA 的两个固定 train 题 `e7a10f8_3`、`29caf6f_1`，每题六条。选题来自预先固定的 SHA256 排序，没有按成功标签选题。这 12 条轨迹、官方 21 条规则、judge 模型别名 `gpt-5.6-sol` / high、reward 公式与缩放均未改变。

新版本为 `smoke_v3_calibrated`，在独立 wrapper 中说明三件事：具体规则的 evaluator_instruction 优先于通用 NA 提示；提交的代码不等于全部执行成功，要检查异常之前与之后；各项依据按自己的规则边界判断，不因为最终答案错误就把所有相关项都判 FAIL。

本地增加 R19（零基 rule_id=18）不得返回 NA 的语义校验：原规则明确无 meaningful failure 时给 +1，因此返回 0 会使请求失败并走原有重试机制，**不会把 0 私自改成 +1**。本轮 12 次请求均首次成功，没有触发重试。校准说明没有给出题目答案、旧评分或官方 success。

原始 v2 判定、旧奖励和采样源码均保留。新评分有独立 manifest、提示、响应与源码快照，不能把两版判定混起来使用。

## 评分究竟在哪里、按什么单位做

服务器运行独立 Codex CLI，按实验配置请求 `gpt-5.6-sol` / high。它不是当前聊天助手直接填写评分，也不是本地 Qwen 8B 推理。我们能记录模型别名、请求、响应和用量，不能仅凭别名独立验证远端实际权重版本。

**一次请求读一条完整 rollout，输出 21 项 PASS/FAIL/NA；不是每个 step 都单独输出 21 项。** step 编号用来定位判定证据。六条 rollout 分别判断完，再由本地程序作为同题一组计算 reward。这个 static 版本没有步骤 credit。

judge 能看到公开任务、初始协议与示范、实际编号步骤的模型文本/提交代码/观察、终止原因；看不到官方成功标签、隐藏测试与私有解法。所有请求都通过无工具调用的事件检查。官方终态结果只在评分完成后的诊断表展示。

## 重测结果和调用成本

| 项目 | v2 原始 smoke | v3 校准重测 |
| --- | --- | --- |
| 轨迹 / 完整六条组 | 12 / 2 | 12 / 2 |
| 规则判定 | 252 | 252 |
| PASS / FAIL / NA | 127 / 86 / 39 | 137 / 78 / 37 |
| 相对 v2 改变的判定 | — | 13 / 252 |
| 实际 judge 请求 | 13（含一次额外重试） | 12（无重试） |
| rubric 有非零组内优势 | 2 / 2 | 2 / 2 |
| outcome 有非零组内优势 | 2 / 2 | 2 / 2 |

v3 输入 token 348,628，其中缓存输入 43,008；输出 token 29,190，其中报告的 reasoning token 13,527。缓存和 reasoning 都是相应总量的子项，不重复相加。两路并发，12 次成功请求的耗时之和 669.40 秒；这不是墙钟耗时，也不推算美元账单。

六个数均按 sample 00–05 排列：

| 题目 | v2 reward | v3 reward |
| --- | --- | --- |
| Spotify `e7a10f8_3` | [6.363636, -10, 10, 2, 6, 10] | [8.181818, -10, 10, 4.545455, 8.181818, 10] |
| 短信 `29caf6f_1` | [-1.111111, -5.555556, 5.555556, -8.888889, -6.666667, 3.333333] | [2.222222, -5.555556, 5.555556, -6.666667, -7.647059, 3.333333] |

两组保留的规则分别为 12 条、18 条。它们本来就是官方成功/失败混合组，所以本次没有证明 rubric 能给全失败组增加可靠的学习信号。reward 上升也不是模型进步：模型与轨迹完全没变，变化来自判分口径和 judge 再次调用。

## 复核：修好了哪些，仍有什么问题

- Spotify 02、03、04 的 R19，从 NA 改为 PASS，符合“无 meaningful failure 默认 +1”的原条款。
- 短信 03 的 R01，从 FAIL 改为 PASS：第 2 步打印表达式在参数求值时先报 NameError，没有输出秘密值。
- 固定的同一批 30 项复核：27 项在所查上下文中有支持，3 项仍有规则边界疑问。另复核全部 13 项分数变化：8 项有支持、4 项有边界疑问、1 项有执行依据错误；两批合计 42 个不同的轨迹—规则对。这是当前助手的证据复核，**不是独立人工金标或 judge 准确率**。

新增明确问题在短信 00 的 R10「使用完整工作集」。judge 给 PASS，并说第 10 步按需合并了第二页。但实际代码顺序是：

```text
第 6 行：获取 recommendation_notes 的第 0 页，赋值完成。
第 7 行：search_text_messages 使用不支持的 other_number 参数，抛出异常。
第 8–9 行：如果 notes 满一页，再 extend 第 1 页；没有执行到。
```

因此，“代码写了分页”不能当成“分页实际发生”的证据。第一页面的数据可能已经留下来，后面的分页却没有发生。我们不据此擅自改成某个最终分数，因为 R10 还需要判断实际已获取项目的使用情况；这里能确定的是 **当前 PASS 的一条关键依据不成立**。原响应与 reward 仍保留，问题单另存。

边界项还包括：未实际发送时评价候选消息内容还是动作参数；可见的解析结果错误是否算 recovery 中的 meaningful failure；实时数据上的错误算法与 unsupported assumption 如何区分；查询了正确 app 但没有读取请求细节，是否满足最终决策使用正确来源。它们不应被包装成所有判定已经可靠。

校准 wrapper 使用了这同一批样本暴露的问题，重测因此只检查校准后的行为，**不是独立样本上的泛化检验**。后续安排单独记录在 plans，本报告保留本轮结果。

## 一个真实题目的完整计算：六条 Spotify 轨迹

固定示例为 `e7a10f8_3`：询问最长 Spotify 播放列表的时长，换算成分钟并四舍五入。00–05 对应该题六条已有采样轨迹；使用本次校准后的 judge 原始判定。例题在读取新分数前已固定。

### 第一步：把 21 条规则的判定全部列出来

P = PASS（+1），F = FAIL（−1），NA = 不适用（0）。这里的 0 是判定编码，后面算平均时 NA 不计入分母。R01–R21 按官方规则原顺序编号，对应 JSON 的零基 rule_id 0–20。Codex 只提供这些判定与证据；以下过滤、计数、reward 和 advantage 均由确定性的 Python 代码计算。

| 规则 | 轨迹00 | 轨迹01 | 轨迹02 | 轨迹03 | 轨迹04 | 轨迹05 | 本组计算时 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R01 不暴露秘密值 | P | F | P | P | P | P | 保留：出现过 F |
| R02 完成后停止 | P | P | P | P | P | P | 删除：没有 F |
| R03 取全需要的数据 | P | F | P | P | P | P | 保留：出现过 F |
| R04 正确调用完成接口 | P | F | P | P | P | P | 保留：出现过 F |
| R05 基于实时数据计算 | P | F | P | P | P | P | 保留：出现过 F |
| R06 正确处理时间条件 | NA | NA | NA | NA | NA | NA | 删除：没有 F |
| R07 完整处理项目 | P | F | P | F | P | P | 保留：出现过 F |
| R08 写操作只针对正确目标 | NA | F | NA | NA | NA | NA | 保留：出现过 F |
| R09 使用正确筛选逻辑 | F | F | P | F | F | P | 保留：出现过 F |
| R10 使用完整工作集 | P | F | P | F | P | P | 保留：出现过 F |
| R11 执行所需写操作 | NA | NA | NA | NA | NA | NA | 删除：没有 F |
| R12 验证写操作结果 | NA | NA | NA | NA | NA | NA | 删除：没有 F |
| R13 写入内容准确 | NA | NA | NA | NA | NA | NA | 删除：没有 F |
| R14 使用正确数据来源 | P | F | P | P | P | P | 保留：出现过 F |
| R15 正确认证 | P | P | P | P | P | P | 删除：没有 F |
| R16 获取所需凭据 | P | P | P | P | P | P | 删除：没有 F |
| R17 使用可运行 Python | P | P | P | P | P | P | 删除：没有 F |
| R18 需要时查阅文档 | P | F | P | P | P | P | 保留：出现过 F |
| R19 从失败中恢复 | P | F | P | P | P | P | 保留：出现过 F |
| R20 API 调用有效 | P | F | P | P | P | P | 保留：出现过 F |
| R21 只用允许的工具 | P | P | P | P | P | P | 删除：没有 F |

### 第二步：先按整组六条过滤规则

**逐行检查，而不是每条轨迹自己挑规则。** 只要某规则在这六条里至少有一个 FAIL，就进入该组共同的保留集合 K；全 PASS、全 NA、PASS/NA 混合都删除。六条全 FAIL 仍保留，不能把“全 FAIL”误删。

- 保留 **12 条**：R01、R03、R04、R05、R07、R08、R09、R10、R14、R18、R19、R20。
- 删除 **9 条**：R02、R06、R11、R12、R13、R15、R16、R17、R21。

规则文件本身没有变化。这只是决定本组哪些已有判定参与 reward；换一个题，保留集合可能不同。

读表时可先看几行：R02 六个 PASS，所以删除；R06 六个 NA，也删除；R09 出现 FAIL，所以保留。R08 虽然多数为 NA，但轨迹 01 实际调用 play_music 改变了播放状态，违反只读任务的目标约束，得到 FAIL；因此 R08 也保留。它只进入轨迹 01 的分母，另外五条的该项为 NA，不进分母。

### 第三步：每条轨迹在保留集合里数 PASS、FAIL、NA

| 轨迹 | 保留项中的 PASS 规则 | 保留项中的 FAIL 规则 | 保留项中的 NA 规则 |
| --- | --- | --- | --- |
| 00 | R01、R03、R04、R05、R07、R10、R14、R18、R19、R20 | R09 | R08 |
| 01 | 无 | R01、R03、R04、R05、R07、R08、R09、R10、R14、R18、R19、R20 | 无 |
| 02 | R01、R03、R04、R05、R07、R09、R10、R14、R18、R19、R20 | 无 | R08 |
| 03 | R01、R03、R04、R05、R14、R18、R19、R20 | R07、R09、R10 | R08 |
| 04 | R01、R03、R04、R05、R07、R10、R14、R18、R19、R20 | R09 | R08 |
| 05 | R01、R03、R04、R05、R07、R09、R10、R14、R18、R19、R20 | 无 | R08 |

| 轨迹 | 过滤前 P/F/NA（总数21） | 过滤后 P | 过滤后 F | 过滤后 NA | 分子 P−F | 分母 P+F |
| --- | --- | --- | --- | --- | --- | --- |
| 00 | 15/1/5 | 10 | 1 | 1 | 9 | 11 |
| 01 | 5/12/4 | 0 | 12 | 0 | -12 | 12 |
| 02 | 16/0/5 | 11 | 0 | 1 | 11 | 11 |
| 03 | 13/3/5 | 8 | 3 | 1 | 5 | 11 |
| 04 | 15/1/5 | 10 | 1 | 1 | 9 | 11 |
| 05 | 16/0/5 | 11 | 0 | 1 | 11 | 11 |

### 第四步：逐条代入 reward 公式

$$r_i=10\times\frac{P_i-F_i}{P_i+F_i}$$

P、F 都只数过滤后的规则。NA 不进入分母；若 P+F=0，则 reward=0。这不是除以原来的 21，也不一定除以保留规则总数。10 是本次沿用的奖励缩放。

| 轨迹 | 实际代入 | 精确 reward | 小数 reward |
| --- | --- | --- | --- |
| 00 | 10 × (10−1)/(10+1) = 10 × 9/11 | 90/11 | 8.181818 |
| 01 | 10 × (0−12)/(0+12) = 10 × -12/12 | -10 | -10.000000 |
| 02 | 10 × (11−0)/(11+0) = 10 × 11/11 | 10 | 10.000000 |
| 03 | 10 × (8−3)/(8+3) = 10 × 5/11 | 50/11 | 4.545455 |
| 04 | 10 × (10−1)/(10+1) = 10 × 9/11 | 90/11 | 8.181818 |
| 05 | 10 × (11−0)/(11+0) = 10 × 11/11 | 10 | 10.000000 |

以轨迹 00 为例：保留规则里有 **10 个 PASS、1 个 FAIL、1 个 NA**。因此分子是 10−1=9，分母是 10+1=11，乘以 10 后得到 **8.181818**。

### 第五步：GRPO 再把六个 reward 变成相对优势

**reward 到上一步已经算完。** 下面的 advantage 是训练所用的组内相对信号，不要把两个量混为一谈。本次仅计算，没有执行训练。

$$\bar r=\frac{1}{6}\sum_{i=1}^{6}r_i,\quad s=\sqrt{\frac{\sum_{i=1}^{6}(r_i-\bar r)^2}{6-1}},\quad A_i=\frac{r_i-\bar r}{s+10^{-6}}$$

本组 reward 向量为 **[8.181818, -10.000000, 10.000000, 4.545455, 8.181818, 10.000000]**。

- 六个 reward 的和为 30.909090909，均值 = 30.909090909/6 = **5.151515152**。
- 离均差平方和为 295.316804408；使用样本标准差，所以除以 6−1=5：s = sqrt(295.316804408/5) = **7.685269083**。
- 归一化分母 s+1e−6 = **7.685270083**。

| 轨迹 | reward | reward−组均值 | 除以 s+1e−6 后的 advantage | 官方终态成功（不进入该 reward） |
| --- | --- | --- | --- | --- |
| 00 | 8.181818182 | 3.030303030 | 0.394300135 | 否 |
| 01 | -10.000000000 | -15.151515152 | -1.971500674 | 否 |
| 02 | 10.000000000 | 4.848484848 | 0.630880216 | 是 |
| 03 | 4.545454545 | -0.606060606 | -0.078860027 | 否 |
| 04 | 8.181818182 | 3.030303030 | 0.394300135 | 否 |
| 05 | 10.000000000 | 4.848484848 | 0.630880216 | 是 |

六个 reward 全相同时，约定全部 advantage=0。正优势只表示比本组六条平均分高，不等于官方任务成功；失败轨迹也可能得到正优势。本静态版本没有步骤 credit，若以后训练，该轨迹的相对优势用于其模型生成 token，工具观察和提示不作为生成动作计损失。

判定、过滤、求均值与缩放对齐 [DRACO 官方 Stage 3–4](https://github.com/IBM/draco/blob/main/training/docs/REWARD_PIPELINE.md)。这里展示的是本次真实数据的计算，不是为公式编造的例子。

## 复现与产物

[校准前后逐项对照](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/verdict_changes.json)、[全部 252 项判定及证据](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/all_verdicts.csv)、[逐组 reward / advantage](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/group_rewards.json)、[同批证据复核](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/evidence_review.json)、[新增执行证据问题](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/execution_evidence_issue.json)。

[六条轨迹算例的机器可读数据](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/reward_worked_example.json)、[技术验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/technical_validation.json)、[输入与来源清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/smoke_v3_calibrated/manifest.json)、[校准 wrapper](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step02_static_scores/calibration_v3/judge_wrapper.txt)。

实际评分入口为 `python -u stages/step02_static_scores/smoke_v3.py --execute --workers 2`。结果分析使用 `python stages/step02_static_scores/analyze_calibrated.py`，证据复核与报告归档使用 `python stages/step02_static_scores/finalize_calibrated.py`；后两条只处理现有文件，不调用模型。

本地用 Fraction 重新推导示例六条 reward，独立计算均值、样本标准差与 advantage，与存储结果逐项一致；12 条判定均与被接受的原始响应完全相同，全部输入和冻结来源 hash 匹配。技术验收的 passed 只覆盖这些检查，不表示语义验收通过。

阶段 fingerprint：`60be918e95812cf2baeaae76127d29d7e6e86cc13a898bff8a44ded5c06e1535`。采样 runtime fingerprint 仍为 `0084e5d4cca518ee3fb956a5c6e7cf93d0c12111e5928cf687f1380e12606052`；21 条规则 SHA256 仍为 `3b359e117973a4d0f20047e159a8c3ef5efe8b52a7421e1194744c8aef815358`。

<!-- STEP02_CALIBRATED_SMOKE_END -->

<!-- DRACO_BASELINE_NEWTASKS_START -->
## 2026-10-09：回到原始 DRACO 静态基线，新题启动遇到认证问题

更新：2026-10-09T15:45:42+08:00。

**已退回仅含必要协议适配的原始静态基线，18 条新题输入已准备。实际启动遇到本执行环境的 CLI 认证错误，已停止；有效评分 0/18，不能给出新 reward 或复核结论。**

## 当前实际使用的评分方式

与原始 `smoke_v2` 相同：21 条官方规则原文、官方评分正文、PASS/FAIL/NA 编码、组内过滤和 reward 公式保持不变。只保留 Python fence / 自动结束协议、示范与实际步骤边界、JSON 顶层对象等本地接口适配。

`smoke_v3_calibrated` 中额外的规则边界说明、默认条款优先说明，以及 R19 禁止 NA 的语义校验均未进入当前调用。现仅检查输出结构完整、21 项标题顺序正确、分数为 -1/0/+1、证据和解释非空。R19 的合法 NA 返回不会被额外拒绝，也不会被本地改写为 PASS。

这不是否认先前发现的误判，而是将复现基线与改进 judge 分开。v2/v3 的原始响应、奖励和报告均保留。新题不用于逐题调整提示，评分误差会按实际证据记录。总体决策与后续安排只写在 plans。

## 已冻结的输入和检查

按原排序 `sha256("static-score-v1:20261009:" + task_id)` 取第 3–5 题；全部来自 train，每题六条既有 LoRA 轨迹。

| 题目 | 公开任务概述 | 轨迹数 |
| --- | --- | --- |
| afc0fce_1 | 给最近五天收到的同事 Venmo 付款评论 Thank you! 并点赞 | 6 |
| e85d92a_3 | 查询 Jasper Skye 播放次数最多的 Spotify 歌曲标题 | 6 |
| 7d7fbf6_3 | 将各度假地点的图片目录压缩到指定路径并删除原子目录 | 6 |

选题没有读取 success 标签来筛选；没有重采样。评分前按固定 hash 每题抽出 10 个轨迹—规则对，共 30 项，已写入 analysis_spec.json，但没有可供复核的新判定。

离线验证通过：18 条轨迹 hash 与原采样记录匹配；没有使用 dev；规则和官方评分正文未变；judge 配置等于 v2；同一旧输入构建出的完整 prompt 与 v2 保存文本逐字节一致；隐藏评价与模型元信息的 canary 不影响输入。只有这些离线检查已通过，实际评分链路本次未完成。

## 本次调用实际发生了什么

2026-10-09 15:33（Asia/Shanghai）启动两路并发，使用服务器独立 Codex CLI，请求原配置 `gpt-5.6-sol` / high。没有使用当前聊天助手代填评分，也没有启动本地 Qwen 推理。

前四条轨迹开始过调用；已落盘的 6 个尝试事件流均记录 `401 Unauthorized: Missing bearer or basic authentication in header`，没有完成的模型输出或 usage。另有未完成调用被停止，不能把落盘事件数当成全部网络重连次数，也不能推断精确计费 token。

只读排查显示 `codex login status` 返回 Not logged in，默认凭据文件不存在，常用认证环境变量未设置。没有修改用户登录配置、查找其他账户密钥、替换 judge 模型或打印凭据。认证检查参考 [OpenAI 官方认证说明](https://learn.chatgpt.com/docs/auth)。

本实验的评分主进程及其子进程已停止。数据状态为 **0 个有效判定、0 个完整评分组、无新 reward**；认证失败没有记成模型 FAIL、NA 或 reward=0。原先采样的官方成败数据也没有变化。

## 已准备的恢复入口与产物

恢复入口 `python stages/step02_static_scores/resume_baseline_newtasks.py --execute` 已完成离线检查，当前没有执行评分恢复。它先检查 CLI 登录；可用后将失败目录另行归档，先完成一条请求，再保持最多两条在途任务。发生调用失败时不继续提交其余题目。它只改运行调度，不改 prompt、规则、judge 配置或 reward。

- [冻结清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/manifest.json)、[离线验证](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/offline_validation.json)、[预先固定的抽查项](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/analysis_spec.json)。
- [认证诊断](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/authentication_diagnostic.json)、[运行日志](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/run.log)、[当前状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step02_static_scores/draco_baseline_newtasks_v1/status.json)。
- [原始基线入口](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step02_static_scores/baseline_newtasks.py)、[恢复入口](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step02_static_scores/resume_baseline_newtasks.py)、[结果分析脚本](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step02_static_scores/analyze_baseline_newtasks.py)。

阶段 fingerprint：`0196d8f17de56c9b0ed543960c98eb18567469461522b6e28a65b4057b86f8ed`。原采样源码、模型、540 条轨迹以及 v2/v3 的冻结文件均未修改。本次没有运行全量评分、GRPO 或新 dev。

<!-- DRACO_BASELINE_NEWTASKS_END -->

认证排查补充：用户确认在自己的服务器终端直接输入 codex 可以使用。上文 Not logged in 仅是本助手执行环境中的观测，不能据此断言用户终端未登录。已核对本环境 root、主机 autodl-container-65d14488ce-cd05d5ef；正常 PATH 和实验入口指向同一安装，未发现自定义 provider 被忽略的证据。正在等待可用终端的入口/认证方式以继续对照。
