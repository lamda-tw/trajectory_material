# 静态 Rubric GRPO 实验报告

本报告持续追加实验步骤；时间使用 Asia/Shanghai。

## 当前完成状态

原始 Qwen3-8B 与现有 SFT LoRA 各完成完整 train90 × 6，共 1,080 条轨迹，两边均通过数据验收。本次系列尚无 rubric 评分、GRPO 更新或新 dev 评测结果。

本报告只记录已执行过程、结果与解释。总体规划及后续步骤统一见 [当前待办](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/README.md) 和 [实验计划](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md)。以下按实际发生顺序保留历史记录。

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
